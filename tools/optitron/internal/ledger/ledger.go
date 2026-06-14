// Package ledger is the append-only, hash-chained findings ledger — optitron's
// cross-run novelty memory and tamper-evident audit trail. It is a faithful port
// of tools/optitron/optitroncore.py's chain primitives (mirrored, in turn, from
// the ralph archetype) plus optitron.py's load/append/fsync.
//
// The chain has a single-writer invariant: hashing entry N depends on entry N-1,
// so concurrent appends would corrupt it. Under the concurrent pipeline every
// write therefore goes through one Writer goroutine (an actor) that owns the file
// and serialises appends over a channel — see Writer.
package ledger

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"sync"
)

// GenesisHash is the prev-hash of seq 0.
const GenesisHash = "0000000000000000000000000000000000000000000000000000000000000000"

// Entry is one hash-chained log line: hash = sha256(prev || canon(payload)).
type Entry struct {
	Seq     int            `json:"seq"`
	Prev    string         `json:"prev"`
	Payload map[string]any `json:"payload"`
	Hash    string         `json:"hash"`
}

// canon renders payload as canonical JSON (sorted keys, compact) — the exact
// bytes that get hashed. Go's encoding/json already sorts map keys.
func canon(payload map[string]any) (string, error) {
	b, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

// ChainHash is the link function: sha256(prevHex || canon(payload)).
func ChainHash(prevHex string, payload map[string]any) (string, error) {
	c, err := canon(payload)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256([]byte(prevHex + c))
	return hex.EncodeToString(sum[:]), nil
}

// MakeEntry builds one chained entry; prevHex is GenesisHash for seq 0.
func MakeEntry(prevHex string, seq int, payload map[string]any) (Entry, error) {
	h, err := ChainHash(prevHex, payload)
	if err != nil {
		return Entry{}, err
	}
	return Entry{Seq: seq, Prev: prevHex, Payload: payload, Hash: h}, nil
}

// VerifyChain reports whether entries form a contiguous, untampered chain from
// genesis.
func VerifyChain(entries []Entry) bool {
	prev := GenesisHash
	for i, e := range entries {
		if e.Seq != i || e.Prev != prev {
			return false
		}
		h, err := ChainHash(prev, e.Payload)
		if err != nil || e.Hash != h {
			return false
		}
		prev = e.Hash
	}
	return true
}

// LongestValidPrefix returns the longest untampered chain prefix — the
// boot-recovery counterpart for a torn tail.
func LongestValidPrefix(entries []Entry) []Entry {
	out := make([]Entry, 0, len(entries))
	prev := GenesisHash
	for i, e := range entries {
		h, err := ChainHash(prev, e.Payload)
		if err != nil || e.Seq != i || e.Prev != prev || e.Hash != h {
			break
		}
		out = append(out, e)
		prev = e.Hash
	}
	return out
}

// Load reads the ledger file (one JSON Entry per line). A missing file is an
// empty ledger.
func Load(path string) ([]Entry, error) {
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer f.Close()
	var out []Entry
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 64*1024), 8*1024*1024)
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var e Entry
		if err := json.Unmarshal(line, &e); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, sc.Err()
}

// PriorTitles returns the titles of every found/rejected payload — the dedupe
// memory that stops optitron re-finding the same optimization.
func PriorTitles(entries []Entry) []string {
	var titles []string
	for _, e := range entries {
		ev, _ := e.Payload["event"].(string)
		if ev != "found" && ev != "rejected" {
			continue
		}
		if t, ok := e.Payload["title"].(string); ok && t != "" {
			titles = append(titles, t)
		}
	}
	return titles
}

// Writer is the single-writer ledger actor. It loads the chain once, repairs a
// torn tail, then serialises every Append so the hash chain stays valid even
// when many pipeline goroutines record events concurrently.
type Writer struct {
	mu      sync.Mutex
	path    string
	entries []Entry
}

// Open loads (and tail-repairs) the ledger at path, ready for appends.
func Open(path string) (*Writer, error) {
	entries, err := Load(path)
	if err != nil {
		return nil, err
	}
	if !VerifyChain(entries) {
		entries = LongestValidPrefix(entries)
	}
	return &Writer{path: path, entries: entries}, nil
}

// Append links payload onto the chain and fsyncs it to disk. Safe for concurrent
// callers — the mutex enforces the single-writer invariant.
func (w *Writer) Append(payload map[string]any) (Entry, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	prev := GenesisHash
	if n := len(w.entries); n > 0 {
		prev = w.entries[n-1].Hash
	}
	e, err := MakeEntry(prev, len(w.entries), payload)
	if err != nil {
		return Entry{}, err
	}
	if err := os.MkdirAll(dir(w.path), 0o755); err != nil {
		return Entry{}, err
	}
	f, err := os.OpenFile(w.path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return Entry{}, err
	}
	defer f.Close()
	b, err := json.Marshal(e)
	if err != nil {
		return Entry{}, err
	}
	if _, err := f.Write(append(b, '\n')); err != nil {
		return Entry{}, err
	}
	if err := f.Sync(); err != nil {
		return Entry{}, err
	}
	w.entries = append(w.entries, e)
	return e, nil
}

// PriorTitles snapshots the dedupe memory at open/append time.
func (w *Writer) PriorTitles() []string {
	w.mu.Lock()
	defer w.mu.Unlock()
	return PriorTitles(w.entries)
}

func dir(p string) string {
	for i := len(p) - 1; i >= 0; i-- {
		if p[i] == '/' {
			return p[:i]
		}
	}
	return "."
}

// String renders an entry for CLI replay.
func (e Entry) String() string {
	return fmt.Sprintf("#%d %s %v", e.Seq, e.Hash[:8], e.Payload)
}
