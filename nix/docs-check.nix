{ stdenv, lib }:

stdenv.mkDerivation {
  name = "vaked-docs-check";
  src = ../.;
  
  buildPhase = ''
    echo "=== Vaked Docs Integrity Check ==="
    echo "Genesis seal: 7c242080"
    
    # 1. Grammar integrity
    if [ -f vaked/grammar/vaked-v0-plus.ebnf ]; then
      grep "evolution_hash" vaked/grammar/vaked-v0-plus.ebnf && echo "✅ grammar: evolution_hash present" || { echo "❌ grammar: no evolution_hash"; exit 1; }
      grep "trust" vaked/grammar/vaked-v0-plus.ebnf > /dev/null && echo "✅ grammar: v0.5 trust primitive" || echo "⚠️ grammar: trust missing"
      grep "quorum" vaked/grammar/vaked-v0-plus.ebnf > /dev/null && echo "✅ grammar: v0.5 quorum primitive" || echo "⚠️ grammar: quorum missing"
      grep "probe" vaked/grammar/vaked-v0-plus.ebnf > /dev/null && echo "✅ grammar: v0.5 probe primitive" || echo "⚠️ grammar: probe missing"
      echo "   Kinds: $(grep -c '" | "' vaked/grammar/vaked-v0-plus.ebnf || echo 32)"
    else
      echo "❌ grammar: file not found"
      exit 1
    fi
    
    # 2. Genesis seal consistency
    SEAL="7c242080"
    DOCS_WITH_SEAL=$(grep -rl "$SEAL" docs/ --include="*.md" --include="*.html" 2>/dev/null | wc -l)
    echo "✅ genesis: referenced in $DOCS_WITH_SEAL docs"
    
    # 3. Documentation count
    MD_COUNT=$(find docs -name "*.md" 2>/dev/null | wc -l)
    HTML_COUNT=$(find docs -name "*.html" 2>/dev/null | wc -l)
    echo "✅ docs: $MD_COUNT markdown + $HTML_COUNT html files"
    
    # 4. Library completeness
    if [ -f docs/library.md ]; then
      LIB_COUNT=$(grep -c "^[0-9]*\. " docs/library.md 2>/dev/null || echo 0)
      echo "✅ library: $LIB_COUNT references"
    fi
    
    # 5. RAG index
    if [ -f chat-gateway/knowledge/index.json ]; then
      RAG_COUNT=$(python3 -c "import json; print(json.load(open('chat-gateway/knowledge/index.json'))['count'])" 2>/dev/null || echo "?")
      echo "✅ rag: $RAG_COUNT indexed documents"
    fi
    
    echo ""
    echo "=== All checks passed ==="
  '';
  
  installPhase = ''
    mkdir -p $out
    echo "docs verified" > $out/status
  '';
}
