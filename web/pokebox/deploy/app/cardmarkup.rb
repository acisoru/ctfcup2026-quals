# CardMarkup — the little formatting syntax trainers can use in their bio, box
# titles and descriptions. A safe, whitelisted renderer: it HTML-escapes the
# input first, then turns a fixed set of [tags] into span markup. No templating,
# no evaluation — user text can never become code here.
#
# This is the *intended* way card text is rendered across the site.
module CardMarkup
  require "cgi"

  TAGS = {
    "b"       => ['<strong>', '</strong>'],
    "i"       => ['<em>', '</em>'],
    "shiny"   => ['<span class="tag-shiny">', '</span>'],
    "sparkle" => ['<span class="tag-sparkle">✨', '✨</span>'],
    "fire"    => ['<span class="tag-fire">🔥', '</span>']
  }.freeze

  SELF_CLOSING = {
    "[pokeball]" => '<span class="tag-ball">◓</span>',
    "[heart]"    => '<span class="tag-heart">♥</span>'
  }.freeze

  def self.render(text)
    s = CGI.escapeHTML(text.to_s)
    SELF_CLOSING.each { |tok, html| s = s.gsub(tok, html) }
    TAGS.each do |name, (open, close)|
      s = s.gsub("[#{name}]", open).gsub("[/#{name}]", close)
    end
    s
  end
end
