require "sinatra"
require "sinatra/base"
require "sqlite3"
require "json"
require "securerandom"
require "erb"
require "digest"
require_relative "savefile"
require_relative "cardmarkup"

DB_PATH = ENV.fetch("POKEBOX_DB", "/data/pokebox.db")

class PokeBox < Sinatra::Base
  set :bind, "0.0.0.0"
  set :port, 8000
  set :views, File.expand_path("../../views", __FILE__)
  set :public_folder, File.expand_path("../../public", __FILE__)
  enable :sessions
  set :session_secret, ENV.fetch("SECRET", SecureRandom.hex(32))

  MAX_UPLOAD = 256 * 1024

  def db
    @db ||= begin
      d = SQLite3::Database.new(DB_PATH)
      d.results_as_hash = true
      d
    end
  end

  def current_user
    return nil unless session[:uid]
    @current_user ||= db.get_first_row("SELECT * FROM users WHERE id = ?", session[:uid])
  end

  def require_login!
    redirect "/login" unless current_user
  end

  helpers do
    def h(s) = Rack::Utils.escape_html(s.to_s)
    # Render trainer-authored text through the safe card-markup renderer.
    def cm(s) = CardMarkup.render(s)
  end

  # ---- auth -----------------------------------------------------------------

  get "/" do
    @feed = db.execute(<<~SQL)
      SELECT b.id, b.trainer_name, b.title, b.description, u.username, b.created_at
      FROM boxes b JOIN users u ON u.id = b.user_id
      WHERE b.shared = 1
      ORDER BY b.created_at DESC LIMIT 50
    SQL
    erb :index
  end

  get("/register") { erb :register }

  post "/register" do
    u = params[:username].to_s.strip
    p = params[:password].to_s
    halt 400, erb(:register, locals: { err_msg: "fill both fields" }) if u.empty? || p.empty?
    begin
      db.execute("INSERT INTO users (username, pw) VALUES (?, ?)",
                 [u, Digest::SHA256.hexdigest(p)])
    rescue SQLite3::ConstraintException
      halt 400, erb(:register, locals: { err_msg: "username taken" })
    end
    session[:uid] = db.last_insert_row_id
    redirect "/boxes"
  end

  get("/login") { erb :login }

  post "/login" do
    row = db.get_first_row("SELECT * FROM users WHERE username = ?", params[:username].to_s)
    if row && row["pw"] == Digest::SHA256.hexdigest(params[:password].to_s)
      session[:uid] = row["id"]
      redirect "/boxes"
    else
      halt 401, erb(:login, locals: { err_msg: "bad credentials" })
    end
  end

  get("/logout") { session.clear; redirect "/" }

  # ---- boxes ----------------------------------------------------------------

  get "/boxes" do
    require_login!
    @boxes = db.execute("SELECT * FROM boxes WHERE user_id = ? ORDER BY created_at DESC",
                        current_user["id"])
    erb :boxes
  end

  post "/boxes" do
    require_login!
    file = params[:save]
    halt 400, "no file" unless file && file[:tempfile]
    data = file[:tempfile].read(MAX_UPLOAD + 1)
    halt 413, "save too large" if data.nil? || data.bytesize > MAX_UPLOAD

    begin
      save = SaveFile.parse(data)
    rescue SaveFile::ParseError, StandardError => e
      msg = e.is_a?(SaveFile::ParseError) ? e.message : "not a valid Gen III save"
      @boxes = db.execute("SELECT * FROM boxes WHERE user_id = ? ORDER BY created_at DESC",
                          current_user["id"])
      halt 400, erb(:boxes, locals: { err_msg: "could not read save: #{h(msg)}" })
    end

    # The "team chant" is the party's nicknames run together — a little hype line
    # the trainer card shows off. Built once at upload time and stored verbatim.
    chant = save.party.map(&:nickname).join

    title = params[:title].to_s[0, 60]
    desc  = params[:description].to_s[0, 300]
    party_json = save.party.map { |m|
      { nick: m.nickname, level: m.level, hp: m.hp, max_hp: m.max_hp }
    }.to_json

    db.execute(
      "INSERT INTO boxes (user_id, trainer_name, trainer_id, gender, play_h, play_m, play_s,
                          title, description, party_json, chant, shared, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))",
      [current_user["id"], save.trainer_name, save.trainer_id, save.gender,
       save.play_h, save.play_m, save.play_s, title, desc, party_json, chant]
    )
    redirect "/box/#{db.last_insert_row_id}"
  end

  # ---- profile / bio --------------------------------------------------------

  get "/settings" do
    require_login!
    erb :settings
  end

  post "/settings" do
    require_login!
    db.execute("UPDATE users SET bio = ? WHERE id = ?",
               [params[:bio].to_s[0, 300], current_user["id"]])
    redirect "/u/#{current_user['username']}"
  end

  get "/u/:username" do
    @profile = db.get_first_row("SELECT * FROM users WHERE username = ?", params[:username])
    halt 404, "no such trainer" unless @profile
    @pboxes = db.execute(
      "SELECT id, trainer_name, title, created_at FROM boxes
       WHERE user_id = ? AND shared = 1 ORDER BY created_at DESC",
      @profile["id"]
    )
    erb :profile
  end

  get "/box/:id" do
    box = db.get_first_row("SELECT * FROM boxes WHERE id = ?", params[:id])
    halt 404, "no such box" unless box
    # visible to the owner, or to anyone if shared
    unless box["shared"] == 1 || (current_user && current_user["id"] == box["user_id"])
      halt 403, "this box is private"
    end
    @box = box
    @party = JSON.parse(box["party_json"])
    @owner = db.get_first_row("SELECT username FROM users WHERE id = ?", box["user_id"])["username"]

    # The trainer card shows a battle cry built from the team chant. Instead of
    # running it through the safe card-markup renderer like the other fields,
    # this one takes a shortcut and builds the cheer as a template string.
    @card = ERB.new("A wild cheer erupts: #{box['chant']}!").result(binding)

    @comments = db.execute("SELECT c.body, u.username FROM comments c
                            JOIN users u ON u.id = c.user_id
                            WHERE c.box_id = ? ORDER BY c.id", box["id"])
    erb :box
  end

  post "/box/:id/share" do
    require_login!
    db.execute("UPDATE boxes SET shared = 1 WHERE id = ? AND user_id = ?",
               [params[:id], current_user["id"]])
    redirect "/box/#{params[:id]}"
  end

  post "/box/:id/comment" do
    require_login!
    box = db.get_first_row("SELECT * FROM boxes WHERE id = ?", params[:id])
    halt 404 unless box
    db.execute("INSERT INTO comments (box_id, user_id, body) VALUES (?, ?, ?)",
               [box["id"], current_user["id"], params[:body].to_s[0, 500]])
    redirect "/box/#{params[:id]}"
  end

  run! if app_file == $0
end
