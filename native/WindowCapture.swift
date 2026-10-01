import Foundation
import AppKit
import ScreenCaptureKit
import ImageIO
import UniformTypeIdentifiers

// Capture the selected window's own surface, independent of desktop occlusion.
// No activation, keyboard/mouse events, audio, or whole-display capture.
@main
struct WindowCapture {
    @MainActor
    static func main() async {
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        do {
            guard CommandLine.arguments.count == 3,
                  let id = UInt32(CommandLine.arguments[1]) else {
                throw NSError(domain: "WindowCapture", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "Usage: window-capture WINDOW_ID OUTPUT.png"])
            }
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: false)
            guard let window = content.windows.first(where: { $0.windowID == id }) else {
                throw NSError(domain: "WindowCapture", code: 2,
                              userInfo: [NSLocalizedDescriptionKey: "Locked window unavailable to ScreenCaptureKit"])
            }
            let filter = SCContentFilter(desktopIndependentWindow: window)
            let config = SCStreamConfiguration()
            let scale = Double(filter.pointPixelScale)
            FileHandle.standardError.write(Data(("window=\(id) onscreen=\(window.isOnScreen) frame=\(window.frame) content=\(filter.contentRect) scale=\(scale)\n").utf8))
            config.width = Int((filter.contentRect.width * scale).rounded())
            config.height = Int((filter.contentRect.height * scale).rounded())
            config.showsCursor = false
            config.capturesAudio = false
            config.ignoreShadowsSingleWindow = true
            config.ignoreGlobalClipSingleWindow = true
            config.shouldBeOpaque = true
            config.captureResolution = .best
            let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
            let url = URL(fileURLWithPath: CommandLine.arguments[2])
            guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
                throw NSError(domain: "WindowCapture", code: 3,
                              userInfo: [NSLocalizedDescriptionKey: "Cannot create output image"])
            }
            CGImageDestinationAddImage(destination, image, nil)
            guard CGImageDestinationFinalize(destination) else {
                throw NSError(domain: "WindowCapture", code: 4,
                              userInfo: [NSLocalizedDescriptionKey: "Cannot write output image"])
            }
        } catch {
            FileHandle.standardError.write(Data((String(describing: error) + "\n").utf8))
            exit(1)
        }
    }
}
