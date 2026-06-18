import SwiftUI

// AG-UI/Features/Viewport/RefactoredMatrixView.swift
// GENESIS_SEAL 7c242080 — DOD re-skin. Zero OOP. Flat arrays. Themed via rawValue.

struct RefactoredMatrixView: View {
    @State private var layout = ViewportLayoutState()

    // Flat sample data — array of node row labels.
    private let sampleNodes: [String] = [
        "guardd.egress.membrane",
        "eventd.hashchain.head",
        "vakedz.parse.cache",
        "supervisor.otp.plane",
        "ebpf.policy.manifest",
        "crabcc.symbol.index",
        "surface.operator.deck"
    ]

    var body: some View {
        let p = Int(layout.activeProfile.rawValue)
        let bg = Color(hex: bgHex[p])
        let surface = Color(hex: surfaceHex[p])
        let fg = Color(hex: fgHex[p])
        let dim = Color(hex: dimHex[p])
        let accent = Color(hex: accentHex[p])
        let border = Color(hex: borderHex[p])

        return VStack(spacing: 0) {
            // Header bar
            HStack {
                Text("VIEWPORT")
                    .font(.system(.headline, design: .monospaced))
                    .foregroundColor(accent)
                Spacer()
                Text(profileNames[p])
                    .font(.system(.caption, design: .monospaced))
                    .foregroundColor(dim)
                Button(action: { cycleProfile(&layout) }) {
                    Text("CYCLE")
                        .font(.system(.caption, design: .monospaced))
                        .foregroundColor(bg)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(accent)
                        .cornerRadius(2)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(surface)
            .overlay(
                Rectangle()
                    .frame(height: 1)
                    .foregroundColor(border),
                alignment: .bottom
            )

            // Flat grid/list of node rows
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(Array(sampleNodes.enumerated()), id: \.offset) { idx, node in
                        HStack(spacing: 8) {
                            Text(String(format: "%02d", idx))
                                .font(.system(.caption2, design: .monospaced))
                                .foregroundColor(dim)
                            Circle()
                                .fill(accent)
                                .frame(width: 6, height: 6)
                            Text(node)
                                .font(.system(.body, design: .monospaced))
                                .foregroundColor(fg)
                            Spacer()
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(idx % 2 == 0 ? bg : surface)
                        .overlay(
                            Rectangle()
                                .frame(height: 1)
                                .foregroundColor(border.opacity(0.4)),
                            alignment: .bottom
                        )
                    }
                }
            }

            // Footer
            HStack {
                Text("\(sampleNodes.count) NODES")
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundColor(dim)
                Spacer()
                Text("SEAL 7c242080")
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundColor(dim)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(surface)
            .overlay(
                Rectangle()
                    .frame(height: 1)
                    .foregroundColor(border),
                alignment: .top
            )
        }
        .background(bg)
    }
}

#Preview {
    RefactoredMatrixView()
}
