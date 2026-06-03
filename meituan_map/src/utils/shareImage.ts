import html2canvas from "html2canvas";

export async function captureShareImage(mapEl: HTMLElement | null, fallbackEl: HTMLElement) {
  try {
    if (mapEl) {
      const canvas = await html2canvas(mapEl, { useCORS: true, allowTaint: true, scale: 2, logging: false });
      return canvas.toDataURL("image/png");
    }
  } catch {
    /* cross-origin tiles */
  }
  const canvas = await html2canvas(fallbackEl, { scale: 2, backgroundColor: "#f5f5f7" });
  return canvas.toDataURL("image/png");
}

export function downloadDataUrl(dataUrl: string, filename: string) {
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  a.click();
}