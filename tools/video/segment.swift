// Person masks for "text behind head": one grayscale PNG per input frame.
//   swift tools/video/segment.swift <frames_dir> <masks_dir>
// Uses Apple Vision's person segmentation (on-device, no model download).
import AppKit
import CoreImage
import Foundation
import Vision

let args = CommandLine.arguments
let inDir = URL(fileURLWithPath: args[1]), outDir = URL(fileURLWithPath: args[2])
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
let ctx = CIContext()
let files = try FileManager.default.contentsOfDirectory(atPath: inDir.path).filter { $0.hasSuffix(".png") }.sorted()

let request = VNGeneratePersonSegmentationRequest()
request.qualityLevel = .accurate
request.outputPixelFormat = kCVPixelFormatType_OneComponent8

for name in files {
    let url = inDir.appendingPathComponent(name)
    guard let src = CIImage(contentsOf: url) else { continue }
    let handler = VNImageRequestHandler(ciImage: src)
    try handler.perform([request])
    guard let buf = request.results?.first?.pixelBuffer else { continue }
    var mask = CIImage(cvPixelBuffer: buf)
    mask = mask.transformed(by: CGAffineTransform(scaleX: src.extent.width / mask.extent.width,
                                                  y: src.extent.height / mask.extent.height))
    let out = outDir.appendingPathComponent(name)
    try ctx.writePNGRepresentation(of: mask, to: out, format: .L8, colorSpace: CGColorSpaceCreateDeviceGray())
}
print("masks:", files.count)
