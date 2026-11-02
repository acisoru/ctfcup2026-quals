// Build: g++ -O2 -g -fno-pie -no-pie -Wl,-z,relro -I<boost> src/service.cpp -o service
#include <boost/gil.hpp>
#include <boost/gil/extension/io/targa.hpp>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace gil = boost::gil;

struct Filter
{
    virtual ~Filter() {}
    virtual void apply( int width, int height ) = 0;

    char opts[0x180];
};

struct GrayFilter : Filter
{
    void apply( int width, int height ) override
    {
        if( width < 0 ) width = 0;
        if( height < 0 ) height = 0;
        (void)width; (void)height;
    }
};

struct WarmFilter : Filter
{
    void apply( int width, int height ) override
    {
        if( width > height ) { int t = width; width = height; height = t; }
        (void)width; (void)height;
    }
};

__attribute__((noinline))
static Filter* make_filter( const std::string& name, void* preview_lo, void* preview_hi )
{
    Filter* f;
    if( name == "warm" )
        f = new WarmFilter();
    else
        f = new GrayFilter();

    std::memcpy( f->opts, &preview_lo, sizeof( preview_lo ) );
    std::memcpy( f->opts + sizeof( void* ), &preview_hi, sizeof( preview_hi ) );
    return f;
}

struct MemStream : std::streambuf
{
    MemStream( char* p, std::size_t n ) { setg( p, p, p + n ); }

    pos_type seekoff( off_type off, std::ios_base::seekdir way,
                      std::ios_base::openmode which ) override
    {
        if( !( which & std::ios_base::in ) ) return pos_type( off_type( -1 ) );
        char* base   = eback();
        char* target = ( way == std::ios_base::beg ) ? base + off
                     : ( way == std::ios_base::cur ) ? gptr() + off
                                                     : egptr() + off;
        if( target < base || target > egptr() ) return pos_type( off_type( -1 ) );
        setg( base, target, egptr() );
        return pos_type( target - base );
    }

    pos_type seekpos( pos_type sp, std::ios_base::openmode which ) override
    {
        return seekoff( off_type( sp ), std::ios_base::beg, which );
    }
};

static std::string trim( const std::string& s )
{
    std::size_t a = s.find_first_not_of( " \t" );
    std::size_t b = s.find_last_not_of( " \t\r\n" );
    if( a == std::string::npos ) return "";
    return s.substr( a, b - a + 1 );
}

static void send_status( int fd, const char* status, const std::string& extra )
{
    std::string r = std::string( "HTTP/1.1 " ) + status + "\r\n";
    r += "Server: image-viewer/1.0\r\n";
    r += extra;
    r += "Connection: close\r\n\r\n";
    (void)!::write( fd, r.data(), r.size() );
}

static const char* INDEX_HTML =
    "<!doctype html><html><head><meta charset=utf-8><title>image-viewer</title>"
    "<style>body{font-family:system-ui,sans-serif;max-width:44rem;margin:3rem auto;padding:0 1rem}"
    "textarea{width:100%;height:8rem}button{padding:.5rem 1rem}pre{background:#111;color:#0f0;padding:1rem;overflow:auto}"
    "</style></head><body><h1>image-viewer</h1>"
    "<p>Upload a <b>Targa (.tga)</b> image. The previewer decodes it and runs the selected filter.</p>"
    "<p><input type=file id=f accept=\".tga\"> "
    "<select id=filter><option>gray</option><option>warm</option></select> "
    "<button onclick=go()>Preview</button></p>"
    "<pre id=out>ready.</pre>"
    "<script>async function go(){const f=document.getElementById('f').files[0];"
    "if(!f){document.getElementById('out').textContent='choose a file';return;}"
    "const b=await f.arrayBuffer();const r=await fetch('/process',{method:'POST',"
    "headers:{'X-Filter':document.getElementById('filter').value,'X-Preview-Size':'228','X-Scale':'1','X-Gamma':'1'},"
    "body:b});let t=await r.text();document.getElementById('out').textContent="
    "[...r.headers].map(([k,v])=>k+': '+v).join('\\n')+'\\n\\n'+t;}</script>"
    "</body></html>";

static void send_page( int fd )
{
    char hdr[160];
    int n = std::snprintf( hdr, sizeof( hdr ),
                           "HTTP/1.1 200 OK\r\nServer: image-viewer/1.0\r\n"
                           "Content-Type: text/html; charset=utf-8\r\nContent-Length: %zu\r\n"
                           "Connection: close\r\n\r\n", std::strlen( INDEX_HTML ) );
    (void)!::write( fd, hdr, static_cast<std::size_t>( n ) );
    (void)!::write( fd, INDEX_HTML, std::strlen( INDEX_HTML ) );
}

static void handle_connection( int fd )
{
    std::string head;
    char ch;
    while( head.size() < 0x8000 )
    {
        ssize_t n = ::read( fd, &ch, 1 );
        if( n <= 0 ) { ::close( fd ); return; }
        head.push_back( ch );
        if( head.size() >= 4 && head.compare( head.size() - 4, 4, "\r\n\r\n" ) == 0 )
            break;
    }

    std::size_t clen = 0;
    std::string filter_name = "gray";
    long preview = 0, scale = 1, gamma = 1;
    long win_off = 0, win_len = 0, preview_depth = 24;
    bool is_get = false;

    {
        std::istringstream hs( head );
        std::string line;
        std::getline( hs, line );
        if( line.compare( 0, 3, "GET" ) == 0 ) is_get = true;
        while( std::getline( hs, line ) )
        {
            if( line == "\r" || line.empty() ) break;
            std::size_t c = line.find( ':' );
            if( c == std::string::npos ) continue;
            std::string k = trim( line.substr( 0, c ) );
            std::string v = trim( line.substr( c + 1 ) );
            if( k == "Content-Length" ) clen = std::strtoull( v.c_str(), nullptr, 10 );
            else if( k == "X-Filter" ) filter_name = v;
            else if( k == "X-Preview-Size" ) preview = std::strtol( v.c_str(), nullptr, 10 );
            else if( k == "X-Scale" ) scale = std::strtol( v.c_str(), nullptr, 10 );
            else if( k == "X-Gamma" ) gamma = std::strtol( v.c_str(), nullptr, 10 );
            else if( k == "X-Preview-Offset" ) win_off = std::strtol( v.c_str(), nullptr, 10 );
            else if( k == "X-Preview-Length" ) win_len = std::strtol( v.c_str(), nullptr, 10 );
            else if( k == "X-Preview-Depth" ) preview_depth = std::strtol( v.c_str(), nullptr, 10 );
        }
    }

    if( is_get )
    {
        send_page( fd );
        ::close( fd );
        return;
    }

    std::vector<unsigned char> body( 0x10000, 0 );
    {
        std::size_t want = clen < body.size() ? clen : body.size();
        std::size_t got = 0;
        while( got < want )
        {
            ssize_t n = ::read( fd, body.data() + got, want - got );
            if( n <= 0 ) break;
            got += static_cast<std::size_t>( n );
        }
    }

    void* scratch_lo = std::malloc( static_cast<std::size_t>( preview ) );
    void* scratch_hi = std::malloc( static_cast<std::size_t>( preview ) );
    Filter* filter = make_filter( filter_name, scratch_lo, scratch_hi );
    std::free( scratch_hi );
    std::free( scratch_lo );

    unsigned width = 0, height = 0;
    unsigned char winbuf[1024];
    long win_got = 0;
    try
    {
        MemStream msb( reinterpret_cast<char*>( body.data() ), static_cast<std::size_t>( clen ) );
        std::istream in( &msb );
        gil::rgb8_image_t img;
        gil::read_image( in, img, gil::targa_tag() );

        width  = static_cast<unsigned>( img.width() );
        height = static_cast<unsigned>( img.height() );

        long off = win_off;
        long len = win_len;
        long depth_bytes = preview_depth > 0 ? ( preview_depth + 7 ) / 8 : 3;
        long stride = static_cast<long>( width ) * depth_bytes;
        long frame  = static_cast<long>( height ) * stride;
        if( off < 0 ) off = 0;
        if( len < 0 ) len = 0;
        if( off + len > frame ) len = ( off < frame ) ? frame - off : 0;
        if( len > static_cast<long>( sizeof( winbuf ) ) ) len = static_cast<long>( sizeof( winbuf ) );
        if( off + len > 0 && len > 0 )
        {
            const unsigned char* pix =
                reinterpret_cast<const unsigned char*>( &gil::view( img )( 0, 0 ) );
            for( long i = 0; i < len; ++i )
                winbuf[i] = pix[off + i];
            win_got = len;
        }

        filter->apply( static_cast<int>( scale ), static_cast<int>( gamma ) );
    }
    catch( const std::exception& )
    {
        
    }

    if( win_got > 0 )
    {
        char hdr[192];
        int n = std::snprintf( hdr, sizeof( hdr ),
                               "HTTP/1.1 200 OK\r\nServer: image-viewer/1.0\r\n"
                               "Content-Type: image/x-tga\r\nContent-Length: %ld\r\n"
                               "Connection: close\r\n\r\n", win_got );
        (void)!::write( fd, hdr, static_cast<std::size_t>( n ) );
        (void)!::write( fd, winbuf, static_cast<std::size_t>( win_got ) );
        ::close( fd );
        return;
    }

    std::string info;
    {
        char base[64];
        std::snprintf( base, sizeof( base ), "X-Image: %ux%u\r\n", width, height );
        info = base;
    }
    send_status( fd, "200 OK", info );
    ::close( fd );
}

int main()
{
    int srv = ::socket( AF_INET, SOCK_STREAM, 0 );
    if( srv < 0 ) { std::perror( "socket" ); return 1; }
    int one = 1;
    ::setsockopt( srv, SOL_SOCKET, SO_REUSEADDR, &one, sizeof( one ) );

    const char* port_env = std::getenv( "IMGV_PORT" );
    unsigned short port = port_env ? static_cast<unsigned short>( std::atoi( port_env ) ) : 1337;

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = ::htonl( INADDR_ANY );
    addr.sin_port = ::htons( port );
    if( ::bind( srv, reinterpret_cast<sockaddr*>( &addr ), sizeof( addr ) ) < 0 )
    { std::perror( "bind" ); return 1; }
    if( ::listen( srv, 64 ) < 0 ) { std::perror( "listen" ); return 1; }

    for( ;; )
    {
        int c = ::accept( srv, nullptr, nullptr );
        if( c < 0 ) continue;
        pid_t pid = ::fork();
        if( pid == 0 )
        {
            ::close( srv );
            ::dup2( c, 0 );
            ::dup2( c, 1 );
            ::dup2( c, 2 );
            handle_connection( c );
            ::_exit( 0 );
        }
        ::close( c );
    }
    return 0;
}