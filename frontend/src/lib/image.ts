/** Phone photos can be 5-12 MB. Resize to at most 1600 px and re-encode as JPEG before upload. */

const MAX_SIDE = 1600

export async function compressImage(source: Blob, quality = 0.85): Promise<Blob> {
  const bitmap = await createImageBitmap(source, { imageOrientation: 'from-image' })
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  return canvasToJpeg(canvas, quality)
}

export function canvasToJpeg(canvas: HTMLCanvasElement, quality = 0.85): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('Could not read the photo.'))), 'image/jpeg', quality),
  )
}
