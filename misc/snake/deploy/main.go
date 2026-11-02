package main

import (
	_ "embed"
	"encoding/json"
	"log"
	"math/rand"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gofiber/contrib/websocket"
	"github.com/gofiber/fiber/v2"
)

//go:embed static/index.html
var indexHTML []byte

type config struct {
	addr    string
	winLen  int
	message string
}

func loadConfig() config {
	cfg := config{
		addr:    ":8080",
		winLen:  CellCount,
		message: "ctfcup{test_flag}",
	}
	if v := os.Getenv("ADDR"); v != "" {
		cfg.addr = v
	}
	flagFile := "/flag.txt"
	if v := os.Getenv("FLAG_FILE"); v != "" {
		flagFile = v
	}
	if v := os.Getenv("FLAG"); v != "" {
		cfg.message = v
	} else if data, err := os.ReadFile(flagFile); err == nil && len(strings.TrimSpace(string(data))) > 0 {
		cfg.message = strings.TrimSpace(string(data))
	}
	if v := os.Getenv("WIN_LENGTH"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < 2 || n > CellCount {
			log.Fatalf("WIN_LENGTH must be an integer in [2, %d], got %q", CellCount, v)
		}
		cfg.winLen = n
	}
	return cfg
}

// clientMsg is what the browser sends over the websocket.
type clientMsg struct {
	Type string `json:"type"` // "move" or "reset"
	Dir  int    `json:"dir"`  // 0..5, only for "move"
}

// stateMsg is the full game state pushed to the browser after every message.
type stateMsg struct {
	Type    string `json:"type"` // always "state"
	Radius  int    `json:"radius"`
	Snake   []Cell `json:"snake"`
	Food    *Cell  `json:"food"`
	Length  int    `json:"length"`
	Target  int    `json:"target"`
	Alive   bool   `json:"alive"`
	Won     bool   `json:"won"`
	Message string `json:"message,omitempty"` // only present on win
}

func snapshot(g *Game, message string) stateMsg {
	m := stateMsg{
		Type:   "state",
		Radius: Radius,
		Snake:  g.Snake,
		Food:   g.Food,
		Length: len(g.Snake),
		Target: g.WinLen,
		Alive:  g.Alive,
		Won:    g.Won,
	}
	if g.Won {
		m.Message = message
	}
	return m
}

func serveWS(cfg config) func(*websocket.Conn) {
	return func(c *websocket.Conn) {
		defer c.Close()
		rng := rand.New(rand.NewSource(time.Now().UnixNano()))
		game := NewGame(cfg.winLen, rng)

		send := func() error {
			return c.WriteJSON(snapshot(game, cfg.message))
		}
		if err := send(); err != nil {
			return
		}

		for {
			_, data, err := c.ReadMessage()
			if err != nil {
				return
			}
			var msg clientMsg
			if err := json.Unmarshal(data, &msg); err != nil {
				_ = c.WriteJSON(fiber.Map{"type": "error", "error": "bad json"})
				continue
			}
			switch msg.Type {
			case "move":
				game.Move(msg.Dir)
			case "reset":
				game.Reset()
			default:
				_ = c.WriteJSON(fiber.Map{"type": "error", "error": "unknown message type"})
				continue
			}
			if err := send(); err != nil {
				return
			}
		}
	}
}

func main() {
	cfg := loadConfig()

	app := fiber.New(fiber.Config{
		DisableStartupMessage: true,
		ReadTimeout:           30 * time.Second,
	})

	app.Get("/", func(c *fiber.Ctx) error {
		c.Set(fiber.HeaderContentType, fiber.MIMETextHTMLCharsetUTF8)
		return c.Send(indexHTML)
	})

	app.Use("/ws", func(c *fiber.Ctx) error {
		if websocket.IsWebSocketUpgrade(c) {
			return c.Next()
		}
		return fiber.ErrUpgradeRequired
	})
	app.Get("/ws", websocket.New(serveWS(cfg)))

	log.Printf("snake listening on %s (board cells=%d, win length=%d)", cfg.addr, CellCount, cfg.winLen)
	if err := app.Listen(cfg.addr); err != nil {
		log.Fatal(err)
	}
}
