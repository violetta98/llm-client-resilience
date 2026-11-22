package main

import "golang.org/x/sys/unix"

// monoNS returns absolute CLOCK_MONOTONIC in nanoseconds. All containers on
// the same Linux kernel share this clock (no time namespaces), so mock and
// driver timestamps are directly comparable.
func monoNS() int64 {
	var ts unix.Timespec
	if err := unix.ClockGettime(unix.CLOCK_MONOTONIC, &ts); err != nil {
		panic(err)
	}
	return ts.Nano()
}

// realNS returns CLOCK_REALTIME in nanoseconds (used to map pcap timestamps).
func realNS() int64 {
	var ts unix.Timespec
	if err := unix.ClockGettime(unix.CLOCK_REALTIME, &ts); err != nil {
		panic(err)
	}
	return ts.Nano()
}

// clockPair samples (realtime, monotonic) as close together as possible:
// the pair with the smallest bracket of three samples is kept.
type clockPair struct {
	RealNS int64 `json:"real_ns"`
	MonoNS int64 `json:"mono_ns"`
	ErrNS  int64 `json:"bracket_ns"`
}

func sampleClockPair() clockPair {
	best := clockPair{ErrNS: 1 << 62}
	for i := 0; i < 5; i++ {
		m1 := monoNS()
		r := realNS()
		m2 := monoNS()
		if m2-m1 < best.ErrNS {
			best = clockPair{RealNS: r, MonoNS: m1 + (m2-m1)/2, ErrNS: m2 - m1}
		}
	}
	return best
}
