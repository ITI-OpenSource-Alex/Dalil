package interview

import (
	"errors"
	"time"
)

var ErrInvalidTiming = errors.New("interview: invalid timing configuration")

type Timing struct {
	Part1Expected time.Duration
	Part2Expected time.Duration
	Part3Expected time.Duration
	Prep          time.Duration
	LongTurnMin   time.Duration
	LongTurnMax   time.Duration
}

func DefaultTiming() Timing {
	return Timing{
		Part1Expected: 5 * time.Minute,
		Part2Expected: 4 * time.Minute,
		Part3Expected: 5 * time.Minute,
		Prep:          60 * time.Second,
		LongTurnMin:   60 * time.Second,
		LongTurnMax:   120 * time.Second,
	}
}

func (t Timing) Validate() error {
	if t.Part1Expected <= 0 || t.Part2Expected <= 0 || t.Part3Expected <= 0 ||
		t.Prep <= 0 || t.LongTurnMin <= 0 || t.LongTurnMax < t.LongTurnMin {
		return ErrInvalidTiming
	}
	return nil
}
