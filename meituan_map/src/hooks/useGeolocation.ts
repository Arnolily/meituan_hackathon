import { useEffect } from "react";
import { useAppStore } from "../store/appStore";

/** 地图已以用户位置初始化后，仅更新定位点标记（不再二次 pan） */
export function useGeolocation(setLocationMarker: (lng: number, lat: number) => void) {
  const mapReady = useAppStore((s) => s.mapReady);
  const userMapCenter = useAppStore((s) => s.userMapCenter);
  const startPointMode = useAppStore((s) => s.travelIntent?.startPointMode);

  useEffect(() => {
    if (!mapReady || !userMapCenter || startPointMode !== "currentLocation") return;
    setLocationMarker(userMapCenter[0], userMapCenter[1]);
  }, [mapReady, userMapCenter, startPointMode, setLocationMarker]);
}
