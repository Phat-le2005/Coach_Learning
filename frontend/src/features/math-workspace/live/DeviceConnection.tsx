"use client";
import { useEffect, useState } from "react";
import QRCode from "qrcode";

export function DeviceConnection(props: { page: number; status: string; devices: number; peers: {id: string; label: string}[]; pending: number; error: string;
  onDisconnect: () => void; onClose: () => void }) {
  const [origin, setOrigin] = useState("");
  const [qr, setQr] = useState("");
  const [copied, setCopied] = useState(false);
  const [path, setPath] = useState("");
  useEffect(() => {
    setOrigin(process.env.NEXT_PUBLIC_APP_URL?.trim() || window.location.origin);
    setPath(window.location.pathname);
  }, []);
  let link = "";
  let local = false;
  try {
    const url = new URL(origin);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) throw new Error();
    url.pathname = path; url.search = `?live=1&writing=1&page=${props.page}`; url.hash = "";
    link = url.toString();
    local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  } catch { /* Show validation instead of an unusable QR. */ }
  useEffect(() => {
    let active = true;
    setQr("");
    if (link && !local) void QRCode.toDataURL(link, { width: 220 }).then(value => { if (active) setQr(value); });
    return () => { active = false; };
  }, [link, local]);
  return <dialog open aria-label="Kết nối thiết bị viết" style={{ position: "fixed", inset: 0, margin: "auto", zIndex: 100, maxWidth: 420, width: "90vw", padding: 20, border: "1px solid #bbc", borderRadius: 12 }}>
    <h2>Kết nối thiết bị viết</h2>
    <p>Đăng nhập cùng tài khoản học sinh trên thiết bị viết. Link không cấp quyền truy cập bài làm.</p>
    <label>Địa chỉ frontend dùng chung qua LAN / HTTPS<input aria-label="Địa chỉ frontend LAN" value={origin} onChange={e => setOrigin(e.target.value)} style={{ width: "100%" }} /></label>
    {local ? <p role="alert">localhost chỉ dùng trên laptop. Nhập IP LAN hoặc tên miền đã cấu hình cho cả hai thiết bị.</p> : null}
    {qr ? <img src={qr} alt="QR mở trang viết, cần đăng nhập" width={220} height={220} /> : null}
    <p style={{ overflowWrap: "anywhere" }}>{link || "Địa chỉ chưa hợp lệ"}</p>
    <button type="button" disabled={!link} onClick={async () => {
      try {
        if (navigator.clipboard) { await navigator.clipboard.writeText(link); setCopied(true); }
        else {
          const field = document.createElement("textarea"); field.value = link;
          field.style.position = "fixed"; field.style.opacity = "0"; document.body.appendChild(field);
          field.select(); setCopied(document.execCommand("copy")); field.remove();
        }
      } catch { setCopied(false); }
    }}>{copied ? "Đã sao chép" : "Sao chép link"}</button>
    <p>{props.status} · {props.devices} thiết bị · {props.pending} thao tác chờ xác nhận</p>
    <ul>{props.peers.map((peer, index) => <li key={peer.id}>{peer.label} {index + 1}</li>)}</ul>
    {props.error ? <p role="alert">{props.error}</p> : null}
    <button type="button" onClick={props.onClose}>Đóng</button>{" "}
    <button type="button" onClick={props.onDisconnect}>Ngắt kết nối thiết bị này</button>
  </dialog>;
}
