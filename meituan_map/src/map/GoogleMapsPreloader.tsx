import { useEffect } from "react";
import { importGoogleMapsLibrary, loadGoogleMapsApi } from "./loadGoogleMap";

export function GoogleMapsPreloader() {
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (cancelled) return;
      void loadGoogleMapsApi()
        .then(() => Promise.all([importGoogleMapsLibrary("maps"), importGoogleMapsLibrary("marker")]))
        .catch(() => undefined);
    }, 350);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  return null;
}
