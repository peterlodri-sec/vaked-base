import SwiftUI
public enum UILayoutProfile: UInt8, CaseIterable { case denseMatrixGreen = 0, cleanGraphCyberpunk = 1, tacticalGraveyard = 2 }
@Observable @MainActor public final class ViewportLayoutEngine {
    public var activeProfile: UILayoutProfile = .denseMatrixGreen
    public init() {}
    public func cycleProfile() { let all = UILayoutProfile.allCases; activeProfile = all[Int((activeProfile.rawValue + 1) % UInt8(all.count))] }
}
