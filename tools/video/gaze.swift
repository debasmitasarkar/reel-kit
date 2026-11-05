// gaze.swift <frames_dir>: per frame "name openness pupil_y" (pupil_y: 0 top of eye, 1 bottom)
import Foundation
import Vision
import CoreImage
let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let files = try FileManager.default.contentsOfDirectory(atPath: dir.path).filter { $0.hasSuffix(".jpg") }.sorted()
for name in files {
    guard let img = CIImage(contentsOf: dir.appendingPathComponent(name)) else { continue }
    let r = VNDetectFaceLandmarksRequest()
    try? VNImageRequestHandler(ciImage: img).perform([r])
    guard let f = r.results?.first, let lm = f.landmarks, let le = lm.leftEye, let re = lm.rightEye,
          let lp = lm.leftPupil, let rp = lm.rightPupil else { print(name, "nan nan"); continue }
    func stats(_ eye: VNFaceLandmarkRegion2D, _ pupil: VNFaceLandmarkRegion2D) -> (Double, Double) {
        let p = eye.normalizedPoints
        let xs = p.map { Double($0.x) }, ys = p.map { Double($0.y) }
        let w = xs.max()! - xs.min()!, h = ys.max()! - ys.min()!
        let py = Double(pupil.normalizedPoints[0].y)
        return (h / w, (ys.max()! - py) / max(h, 1e-6))
    }
    let a = stats(le, lp), b = stats(re, rp)
    print(name, String(format: "%.3f %.3f", (a.0 + b.0) / 2, (a.1 + b.1) / 2))
}
