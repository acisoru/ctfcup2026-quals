package main

import (
	"math/rand"
	"testing"
)

func TestCellCount(t *testing.T) {
	if CellCount != 61 {
		t.Fatalf("side-5 hexagon should have 61 cells, got %d", CellCount)
	}
}

func TestWallKills(t *testing.T) {
	g := NewGame(CellCount, rand.New(rand.NewSource(1)))
	for i := 0; i < Radius; i++ {
		if !g.Move(0) || !g.Alive {
			t.Fatalf("step %d should be safe", i)
		}
	}
	g.Move(0)
	if g.Alive {
		t.Fatal("moving off the board should kill the snake")
	}
	if g.Move(0) {
		t.Fatal("dead snake must not move")
	}
}

func TestEatAndGrow(t *testing.T) {
	g := NewGame(CellCount, rand.New(rand.NewSource(1)))
	g.Food = &Cell{1, 0}
	g.Move(0)
	if len(g.Snake) != 2 || g.Snake[0] != (Cell{1, 0}) || g.Snake[1] != (Cell{0, 0}) {
		t.Fatalf("unexpected snake after eating: %v", g.Snake)
	}
	if g.Food == nil || *g.Food == (Cell{1, 0}) || *g.Food == (Cell{0, 0}) {
		t.Fatalf("food must be respawned on a free cell, got %v", g.Food)
	}
}

func TestSelfCollisionAndTailFollow(t *testing.T) {
	g := NewGame(CellCount, rand.New(rand.NewSource(1)))
	// Build a length-3 snake by feeding it twice.
	g.Food = &Cell{1, 0}
	g.Move(0)
	g.Food = &Cell{2, 0}
	g.Move(0)
	if len(g.Snake) != 3 {
		t.Fatalf("expected length 3, got %d", len(g.Snake))
	}
	// Reversing into the neck is a collision.
	g.Move(3)
	if g.Alive {
		t.Fatal("moving into the neck should kill the snake")
	}

	// A 6-cell loop: the head may step onto the current tail cell.
	g = NewGame(CellCount, rand.New(rand.NewSource(1)))
	g.Food = &Cell{1, 0}
	g.Move(0) // snake: (1,0),(0,0)
	g.Food = &Cell{2, -1}
	g.Move(1) // snake: (2,-1),(1,0),(0,0)
	g.Food = &Cell{2, -2}
	g.Move(2) // snake: (2,-2),(2,-1),(1,0),(0,0)
	g.Food = &Cell{1, -2}
	g.Move(3) // (1,-2),(2,-2),(2,-1),(1,0),(0,0)
	g.Food = &Cell{0, -1}
	g.Move(4) // (0,-1),(1,-2),(2,-2),(2,-1),(1,0),(0,0)
	g.Food = nil
	g.Move(5) // head -> (0,0) which is the tail; tail moves away
	if !g.Alive {
		t.Fatal("stepping onto the vacating tail cell must be allowed")
	}
	if g.Snake[0] != (Cell{0, 0}) || len(g.Snake) != 6 {
		t.Fatalf("unexpected snake %v", g.Snake)
	}
}

func TestWin(t *testing.T) {
	g := NewGame(3, rand.New(rand.NewSource(1)))
	g.Food = &Cell{1, 0}
	g.Move(0)
	g.Food = &Cell{2, 0}
	g.Move(0)
	if !g.Won || !g.Alive {
		t.Fatalf("expected win at length 3: won=%v alive=%v", g.Won, g.Alive)
	}
	if g.Move(0) {
		t.Fatal("finished game must not accept moves")
	}
	g.Reset()
	if g.Won || len(g.Snake) != 1 || g.Food == nil {
		t.Fatal("reset should start a fresh game")
	}
}

func TestFullBoardIsReachable(t *testing.T) {
	// Feed the snake deterministically along a spiral until it fills the board.
	g := NewGame(CellCount, rand.New(rand.NewSource(1)))
	path := spiral()
	if len(path) != CellCount {
		t.Fatalf("spiral covers %d cells, want %d", len(path), CellCount)
	}
	for i := 1; i < len(path); i++ {
		cur, next := path[i-1], path[i]
		dir := -1
		for d, off := range Dirs {
			if (Cell{cur.Q + off.Q, cur.R + off.R}) == next {
				dir = d
			}
		}
		if dir < 0 {
			t.Fatalf("spiral step %d is not adjacent: %v -> %v", i, cur, next)
		}
		g.Food = &next
		if !g.Move(dir) || !g.Alive {
			t.Fatalf("died at step %d (%v)", i, next)
		}
	}
	if !g.Won || len(g.Snake) != CellCount {
		t.Fatalf("expected full-board win, got won=%v len=%d", g.Won, len(g.Snake))
	}
}

// spiral returns a Hamiltonian path over the board starting at the centre and
// walking outwards ring by ring.
func spiral() []Cell {
	path := []Cell{{0, 0}}
	for ring := 1; ring <= Radius; ring++ {
		// Enter the ring at a cell adjacent to where the previous ring ended,
		// then walk the whole ring cycle from there.
		prev := path[len(path)-1]
		rc := ringCells(ring)
		idx := -1
		for i, cand := range rc {
			if dist(prev, cand) == 1 {
				idx = i
				break
			}
		}
		if idx < 0 {
			panic("no adjacent entry into ring")
		}
		for i := 0; i < len(rc); i++ {
			path = append(path, rc[(idx+i)%len(rc)])
		}
	}
	return path
}

func ringCells(ring int) []Cell {
	var out []Cell
	c := Cell{ring, 0}
	// walk in order of directions 2,3,4,5,0,1 from (ring,0) going counter-clockwise
	for _, d := range []int{2, 3, 4, 5, 0, 1} {
		for i := 0; i < ring; i++ {
			out = append(out, c)
			c = Cell{c.Q + Dirs[d].Q, c.R + Dirs[d].R}
		}
	}
	return out
}

func dist(a, b Cell) int {
	dq, dr := a.Q-b.Q, a.R-b.R
	return (abs(dq) + abs(dr) + abs(dq+dr)) / 2
}
