// Vaked Docs — BM25 search ranking unit tests.
// GENESIS_SEAL: 7c242080
package main

import (
	"math"
	"testing"
)

func TestNewBM25Scorer(t *testing.T) {
	ix := NewIndexer()
	ix.AddDocument("pkg/a", "query one", "hello world")
	ix.AddDocument("pkg/b", "query two", "zig language")

	s := NewBM25Scorer(ix)
	if s == nil {
		t.Fatal("NewBM25Scorer returned nil")
	}
	if s.K1 != 1.5 {
		t.Errorf("expected K1=1.5, got %f", s.K1)
	}
	if s.B != 0.75 {
		t.Errorf("expected B=0.75, got %f", s.B)
	}
	if s.AvgDocLength <= 0 {
		t.Errorf("expected positive AvgDocLength, got %f", s.AvgDocLength)
	}
}

func TestBM25Score(t *testing.T) {
	ix := NewIndexer()
	doc1 := ix.AddDocument("ziglang/zig", "std.Build API", "build system api zig")
	doc2 := ix.AddDocument("nixos/nixpkgs", "buildRustPackage", "nix build rust package")

	s := NewBM25Scorer(ix)

	// Score for "build" in doc1 (1 occurrence) vs doc2 (1 occurrence)
	// Both have same tf, but IDF depends on df
	terms := []string{"build"}
	score1 := s.Score(terms, doc1)
	score2 := s.Score(terms, doc2)

	if score1 <= 0 {
		t.Errorf("expected positive score for 'build' in doc1, got %f", score1)
	}
	if score2 <= 0 {
		t.Errorf("expected positive score for 'build' in doc2, got %f", score2)
	}

	// Score for "zig" — only in doc1
	termsZig := []string{"zig"}
	scoreZig1 := s.Score(termsZig, doc1)
	scoreZig2 := s.Score(termsZig, doc2)

	if scoreZig1 <= 0 {
		t.Errorf("expected positive score for 'zig' in doc1, got %f", scoreZig1)
	}
	if scoreZig2 != 0 {
		t.Errorf("expected zero score for 'zig' in doc2, got %f", scoreZig2)
	}
}

func TestBM25ScorerEmptyIndex(t *testing.T) {
	ix := NewIndexer()
	s := NewBM25Scorer(ix)

	score := s.Score([]string{"anything"}, 1)
	if score != 0 {
		t.Errorf("expected score=0 for empty index, got %f", score)
	}
}

func TestBM25Search(t *testing.T) {
	ix := NewIndexer()
	ix.AddDocument("ziglang/zig", "std.Build API", "the zig build system provides a way to compile and link programs")
	ix.AddDocument("ziglang/zig", "ArrayListUnmanaged", "use arraylistunmanaged with an allocator for dynamic arrays")
	ix.AddDocument("nixos/nixpkgs", "buildRustPackage", "buildRustPackage helps build rust crates from source")
	ix.AddDocument("tauri-apps/tauri", "plugin system", "the tauri plugin system enables extending functionality")

	s := NewBM25Scorer(ix)

	// Search for "build"
	results := s.Search("build", 10)
	if len(results) == 0 {
		t.Fatal("expected at least 1 result for 'build'")
	}

	// "build" appears in zig build system and nixos buildRustPackage
	// Should rank them higher than others
	top := results[0]
	if top.Score <= 0 {
		t.Errorf("expected positive score for top result, got %f", top.Score)
	}

	// Search for something very specific
	results2 := s.Search("zig build", 5)
	if len(results2) == 0 {
		t.Fatal("expected at least 1 result for 'zig build'")
	}
	if results2[0].PackageID != "ziglang/zig" {
		t.Errorf("expected top result from ziglang/zig, got %s", results2[0].PackageID)
	}
}

func TestBM25EmptyQuery(t *testing.T) {
	ix := NewIndexer()
	ix.AddDocument("pkg", "q", "some content")
	s := NewBM25Scorer(ix)

	results := s.Search("", 10)
	if len(results) != 0 {
		t.Errorf("expected 0 results for empty query, got %d", len(results))
	}
}

func TestBM25TopK(t *testing.T) {
	ix := NewIndexer()
	for i := 0; i < 10; i++ {
		ix.AddDocument("pkg", "q", "build system zig lang")
	}

	s := NewBM25Scorer(ix)

	results3 := s.Search("build", 3)
	if len(results3) > 3 {
		t.Errorf("expected at most 3 results with topK=3, got %d", len(results3))
	}

	resultAll := s.Search("build", 0)
	if len(resultAll) == 0 {
		t.Error("expected results with topK=0 (meaning all)")
	}
}

func TestBM25ScoreOrdering(t *testing.T) {
	ix := NewIndexer()
	ix.AddDocument("pkg/a", "build system", "build system zig")
	ix.AddDocument("pkg/b", "rust build", "rust build cargo")
	ix.AddDocument("pkg/c", "other topic", "unrelated content here")

	s := NewBM25Scorer(ix)
	results := s.Search("build", 5)

	if len(results) < 2 {
		t.Fatalf("expected at least 2 results for 'build', got %d", len(results))
	}

	// Results should be sorted descending by score
	for i := 1; i < len(results); i++ {
		if results[i].Score > results[i-1].Score {
			t.Errorf("results not sorted: index %d (score=%f) > index %d (score=%f)",
				i, results[i].Score, i-1, results[i-1].Score)
		}
	}
}

func TestTokenizeAll(t *testing.T) {
	tests := []struct {
		input string
		want  []string
	}{
		{"hello world", []string{"hello", "world"}},
		{"std.Build API", []string{"std.build", "api"}},
		{"ArrayListUnmanaged", []string{"arraylistunmanaged"}},
		{"", nil},
		{"  ", nil},
	}
	for _, tt := range tests {
		got := TokenizeAll(tt.input)
		if !stringSliceEqualWT(got, tt.want) {
			t.Errorf("TokenizeAll(%q) = %v, want %v", tt.input, got, tt.want)
		}
	}
}

// TestIDFConvergence verifies that IDF behaves correctly as docs are added.
func TestIDFConvergence(t *testing.T) {
	ix := NewIndexer()
	ix.AddDocument("pkg", "q", "common common unique")

	idfUnique := ix.IDF("unique")
	idfCommon := ix.IDF("common")

	// "unique" appears in 1 of 1 docs -> low idf (log(1 + (1-1+0.5)/(1+0.5))≈0.405)
	// "common" appears in 1 of 1 docs -> same idf
	if math.Abs(idfUnique-idfCommon) > 0.001 {
		t.Errorf("expected equal IDF when both appear in all docs: unique=%f common=%f",
			idfUnique, idfCommon)
	}

	// Add doc2 without "unique"
	ix.AddDocument("pkg2", "q2", "common only here")

	idfUnique2 := ix.IDF("unique")
	idfCommon2 := ix.IDF("common")

	// Now "unique" appears in 1 of 2 docs -> higher idf
	if idfUnique2 <= idfCommon2 {
		t.Errorf("expected unique IDF > common IDF after adding doc without unique: unique=%f common=%f",
			idfUnique2, idfCommon2)
	}
}

func stringSliceEqualWT(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
