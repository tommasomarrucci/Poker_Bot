import Foundation
import AppKit
import ScreenCaptureKit
import CoreMedia
import CoreVideo

final class Receiver: NSObject, SCStreamOutput, SCStreamDelegate, @unchecked Sendable {
    let condition = NSCondition()
    var pixels: Data?
    var dimensions: [String: Any] = [:]
    var updatedAt = 0.0
    var observedAt = 0.0
    var failure: String?

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        condition.lock()
        failure = error.localizedDescription
        condition.broadcast()
        condition.unlock()
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sample: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, sample.isValid,
              let attachments = CMSampleBufferGetSampleAttachmentsArray(sample, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let rawStatus = attachments.first?[.status] as? Int,
              let status = SCFrameStatus(rawValue: rawStatus) else { return }
        if status == .started { return }
        if status == .idle {
            condition.lock()
            observedAt = Date().timeIntervalSince1970
            condition.broadcast()
            condition.unlock()
            return
        }
        guard status == .complete, let buffer = sample.imageBuffer else {
            condition.lock()
            failure = "Window stream suspended or blank (status \(rawStatus))"
            condition.broadcast()
            condition.unlock()
            return
        }
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        guard let address = CVPixelBufferGetBaseAddress(buffer) else {
            CVPixelBufferUnlockBaseAddress(buffer, .readOnly)
            return
        }
        let stride = CVPixelBufferGetBytesPerRow(buffer)
        let height = CVPixelBufferGetHeight(buffer)
        let data = Data(bytes: address, count: stride * height)
        let width = CVPixelBufferGetWidth(buffer)
        CVPixelBufferUnlockBaseAddress(buffer, .readOnly)
        condition.lock()
        pixels = data
        dimensions = ["format": "BGRA", "width": width, "height": height, "stride": stride]
        updatedAt = Date().timeIntervalSince1970
        observedAt = updatedAt
        failure = nil
        condition.broadcast()
        condition.unlock()
    }

    func response() -> (Data, [String: Any]) {
        condition.lock()
        defer { condition.unlock() }
        let deadline = Date().addingTimeInterval(5)
        while pixels == nil && failure == nil {
            if !condition.wait(until: deadline) { break }
        }
        let age = Date().timeIntervalSince1970 - observedAt
        if let failure = failure {
            return (Data(), ["error": failure])
        }
        guard let pixels = pixels, age < 3 else {
            return (Data(), ["error": "No fresh window-stream frames; window may be suspended", "age_seconds": age])
        }
        var info = dimensions
        info["frame_updated_at"] = updatedAt
        info["stream_observed_at"] = observedAt
        info["frame_age_seconds"] = Date().timeIntervalSince1970 - updatedAt
        return (pixels, info)
    }
}

@main
struct WindowStream {
    @MainActor
    static func main() async {
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        do {
            guard CommandLine.arguments.count == 3, let id = UInt32(CommandLine.arguments[1]),
                  let fps = Double(CommandLine.arguments[2]), fps.isFinite, fps > 0, fps <= 30 else {
                throw NSError(domain: "WindowStream", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "Usage: window-stream WINDOW_ID FPS (0 < FPS <= 30)"])
            }
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: false)
            guard let window = content.windows.first(where: { $0.windowID == id }) else {
                throw NSError(domain: "WindowStream", code: 2,
                              userInfo: [NSLocalizedDescriptionKey: "Locked window unavailable"])
            }
            let filter = SCContentFilter(desktopIndependentWindow: window)
            let config = SCStreamConfiguration()
            config.width = min(1710, Int((filter.contentRect.width * Double(filter.pointPixelScale)).rounded()))
            config.height = Int((filter.contentRect.height / filter.contentRect.width * Double(config.width)).rounded())
            config.pixelFormat = kCVPixelFormatType_32BGRA
            config.minimumFrameInterval = CMTime(seconds: 1 / fps, preferredTimescale: 600)
            config.queueDepth = 3
            config.showsCursor = false
            config.capturesAudio = false
            config.ignoreShadowsSingleWindow = true
            config.ignoreGlobalClipSingleWindow = true
            config.shouldBeOpaque = true
            let receiver = Receiver()
            let stream = SCStream(filter: filter, configuration: config, delegate: receiver)
            try stream.addStreamOutput(receiver, type: .screen,
                                       sampleHandlerQueue: DispatchQueue(label: "poker-reader.frames"))
            try await stream.startCapture()
            // Receive requests off the main actor so AppKit can service its runloop.
            await Task.detached {
                while let line = readLine() {
                    if line != "capture" { break }
                    let (pixels, info) = receiver.response()
                    var header = info
                    header["bytes"] = pixels.count
                    if let json = try? JSONSerialization.data(withJSONObject: header) {
                        FileHandle.standardOutput.write(json)
                        FileHandle.standardOutput.write(Data([10]))
                        FileHandle.standardOutput.write(pixels)
                    }
                }
            }.value
            try await stream.stopCapture()
        } catch {
            FileHandle.standardError.write(Data((String(describing: error) + "\n").utf8))
            exit(1)
        }
    }
}
