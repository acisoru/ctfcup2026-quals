package main

import "math/rand"

// BoardSide is the number of cells along one edge of the hexagonal board.
const BoardSide = 5

// Radius is the hex distance from the centre cell to an edge cell.
const Radius = BoardSide - 1

// Cell is an axial hex coordinate. The third cube coordinate is -Q-R.
type Cell struct {
	Q int `json:"q"`
	R int `json:"r"`
}

// Dirs lists the six neighbour offsets, indexed 0..5 counter-clockwise
// starting from "east" for pointy-top cells: E, NE, NW, W, SW, SE.
var Dirs = [6]Cell{{1, 0}, {1, -1}, {0, -1}, {-1, 0}, {-1, 1}, {0, 1}}

func abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}

// InBoard reports whether c lies inside the hexagonal board.
func InBoard(c Cell) bool {
	return abs(c.Q) <= Radius && abs(c.R) <= Radius && abs(c.Q+c.R) <= Radius
}

// AllCells enumerates every cell of the board.
func AllCells() []Cell {
	var cells []Cell
	for q := -Radius; q <= Radius; q++ {
		for r := -Radius; r <= Radius; r++ {
			c := Cell{q, r}
			if InBoard(c) {
				cells = append(cells, c)
			}
		}
	}
	return cells
}

// CellCount is the total number of cells on the board (61 for side 5).
var CellCount = len(AllCells())

// Game is a single snake game. It is not safe for concurrent use.
type Game struct {
	Snake  []Cell // head first
	Food   *Cell
	Alive  bool
	Won    bool
	WinLen int
	rng    *rand.Rand
}

// NewGame creates a game that is won once the snake reaches winLen cells.
func NewGame(winLen int, rng *rand.Rand) *Game {
	g := &Game{WinLen: winLen, rng: rng}
	g.Reset()
	return g
}

// Reset puts a length-1 snake in the centre and spawns food.
func (g *Game) Reset() {
	g.Snake = []Cell{{0, 0}}
	g.Alive = true
	g.Won = false
	g.Food = nil
	g.placeFood()
}

func (g *Game) occupied(c Cell) bool {
	for _, s := range g.Snake {
		if s == c {
			return true
		}
	}
	return false
}

func (g *Game) placeFood() {
	var free []Cell
	for _, c := range AllCells() {
		if !g.occupied(c) {
			free = append(free, c)
		}
	}
	if len(free) == 0 {
		g.Food = nil
		return
	}
	c := free[g.rng.Intn(len(free))]
	g.Food = &c
}

// Move advances the snake one step in direction dir (0..5).
// It returns false if the move was rejected (bad direction or finished game).
func (g *Game) Move(dir int) bool {
	if dir < 0 || dir >= len(Dirs) || !g.Alive || g.Won {
		return false
	}
	head := g.Snake[0]
	next := Cell{head.Q + Dirs[dir].Q, head.R + Dirs[dir].R}

	if !InBoard(next) {
		g.Alive = false
		return true
	}

	eating := g.Food != nil && *g.Food == next

	// The tail cell frees up this turn unless we grow, so it is not a collision.
	body := g.Snake
	if !eating {
		body = body[:len(body)-1]
	}
	for _, s := range body {
		if s == next {
			g.Alive = false
			return true
		}
	}

	if eating {
		g.Snake = append([]Cell{next}, g.Snake...)
		g.Food = nil
	} else {
		copy(g.Snake[1:], g.Snake[:len(g.Snake)-1])
		g.Snake[0] = next
	}

	if len(g.Snake) >= g.WinLen {
		g.Won = true
		g.Food = nil
		return true
	}
	if eating {
		g.placeFood()
	}
	return true
}
