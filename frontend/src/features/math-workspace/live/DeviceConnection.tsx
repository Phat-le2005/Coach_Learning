"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, Laptop, LoaderCircle, RefreshCw, ShieldCheck, Smartphone, Unplug, X } from "lucide-react";
import QRCode from "qrcode";
import { deviceRequest, type DevicePairing } from "./device-client";
import styles from "./writing.module.css";

export function DeviceConnection(props: {attemptId: string; page: number; pairing: DevicePairing | null;
  onPairingChange: (value: DevicePairing) => void; onClose: () => void}) {
  const {attemptId, page} = props;
  const [pairing, setPairing] = useState(props.pairing);
  const [appOrigin, setAppOrigin] = useState("");
  const [qr, setQr] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [network, setNetwork] = useState<{enabled: boolean; origin: string | null; origins: string[]; generation: string} | null>(null);
  const [networkChanged, setNetworkChanged] = useState(false);
  const recoveredNetwork = useRef("");
  const dialog = useRef<HTMLDialogElement>(null);
  const starting = useRef(false);
  const pairingRef = useRef(pairing); pairingRef.current = pairing;
  const callback = useRef(props.onPairingChange); callback.current = props.onPairingChange;
  const endpoint = `/api/v2/math-solutions/attempts/${attemptId}/ink/pairings`;
  const save = useCallback((value: DevicePairing) => {
    const next = {...value, code: value.status === "WAITING" ? value.code ?? pairingRef.current?.code : undefined};
    pairingRef.current = next; setPairing(next); callback.current(next);
  }, []);
  const create = useCallback(async () => {
    setBusy(true); setError("");
    try {
      const previous = pairingRef.current;
      if (previous && !["REVOKED", "EXPIRED"].includes(previous.status)) {
        try {await deviceRequest(`${endpoint}/${previous.id}/revoke`, {});}
        catch (failure) {if (![404, 410].includes((failure as {status?: number}).status ?? 0)) throw failure;}
      }
      save(await deviceRequest<DevicePairing>(endpoint, {page_index: page}));
    } catch (failure) {setError(failure instanceof Error ? failure.message : "Chưa tạo được mã kết nối.");}
    finally {setBusy(false);}
  }, [endpoint, page, save]);
  useEffect(() => {
    setAppOrigin(process.env.NEXT_PUBLIC_APP_URL?.trim() || window.location.origin);
    dialog.current?.showModal(); const node = dialog.current;
    return () => node?.close();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const response = await fetch("/api/lan", {cache: "no-store", signal: controller.signal});
        if (response.ok) setNetwork(await response.json());
      } catch { /* Existing connection/error UI handles unavailable service. */ }
    };
    void refresh(); const timer = setInterval(() => void refresh(), 5000);
    return () => {controller.abort(); clearInterval(timer);};
  }, []);
  useEffect(() => {
    if (!network?.enabled || !network.origin || !pairing?.origin || network.origins.includes(pairing.origin)
        || busy || recoveredNetwork.current === network.generation) return;
    recoveredNetwork.current = network.generation;
    setNetworkChanged(true);
    void create();
  }, [network, pairing?.origin, busy, create]);
  useEffect(() => {
    if (!props.pairing && !starting.current) {starting.current = true; void create();}
  }, [props.pairing, create]);
  useEffect(() => {
    if (!pairing?.id || ["REVOKED", "EXPIRED"].includes(pairing.status)) return;
    let active = true;
    const poll = async () => {
      try {const value = await deviceRequest<DevicePairing>(`${endpoint}/${pairing.id}`); if (active) save(value);}
      catch (failure) {if (active) setError(failure instanceof Error ? failure.message : "Mất kết nối.");}
    };
    void poll(); const timer = setInterval(() => void poll(), 1500);
    return () => {active = false; clearInterval(timer);};
  }, [pairing?.id, pairing?.status, endpoint, save]);
  let link = "";
  const reachable = !network?.enabled || Boolean(pairing?.origin && network.origins.includes(pairing.origin));
  try {const target = new URL("/write", pairing?.origin || appOrigin); if (reachable && ["http:", "https:"].includes(target.protocol) && pairing?.code) {target.hash = `code=${pairing.code}`; link = target.toString();}} catch { /* Browser origin loads after mount. */ }
  useEffect(() => {
    let active = true; setQr("");
    if (link) void QRCode.toDataURL(link, {width: 256, margin: 1, color: {dark: "#193d34", light: "#ffffff"}}).then(value => {if (active) setQr(value);});
    return () => {active = false;};
  }, [link]);
  const action = async (command: "approve" | "revoke") => {
    if (!pairing) return; setBusy(true); setError("");
    try {save(await deviceRequest<DevicePairing>(`${endpoint}/${pairing.id}/${command}`, {}));}
    catch (failure) {setError(failure instanceof Error ? failure.message : "Chưa thực hiện được.");}
    finally {setBusy(false);}
  };
  const expired = pairing && ["REVOKED", "EXPIRED"].includes(pairing.status);
  return <dialog ref={dialog} className={styles.connectionDialog} aria-labelledby="device-connection-title" onCancel={props.onClose} onClick={e => {if (e.target === e.currentTarget) props.onClose();}}>
    <div className={styles.dialogContent}>
      <button type="button" className={styles.closeButton} aria-label="Đóng" onClick={props.onClose}><X size={20}/></button>
      <div className={styles.deviceIllustration} aria-hidden="true"><Laptop size={32}/><span/><Smartphone size={25}/></div>
      <h2 id="device-connection-title">Viết thoải mái hơn<br/>trên điện thoại, iPad</h2>
      <p className={styles.description}>Viết trên màn hình cảm ứng. Nét bút xuất hiện ngay trong bài làm trên máy tính.</p>
      {networkChanged ? <p role="status" className={styles.expiryNote}>Mạng đã thay đổi. Quét mã mới để kết nối lại.</p> : null}
      {network?.enabled && !network.origin ? <p role="alert" className={styles.error}>Chưa tìm thấy mạng nội bộ. Kết nối Wi-Fi hoặc cáp mạng rồi thử lại.</p> : null}
      {pairing?.status === "ACTIVE" ? <div className={styles.successCard}>
        <span className={styles.successIcon}><Check size={30}/></span><h3>Đã kết nối {pairing.device_name}</h3>
        <p>Bạn có thể bắt đầu viết. Mọi nét bút được lưu trong bài này.</p>
        <button type="button" className={styles.primaryButton} onClick={props.onClose}>Tiếp tục làm bài</button>
        <button type="button" className={styles.textButton} disabled={busy} onClick={() => void action("revoke")}><Unplug size={15}/>Ngắt thiết bị</button>
      </div> : pairing?.status === "PENDING" ? <div className={styles.approvalCard}>
        <Smartphone size={30}/><h3>{pairing.device_name} đang muốn kết nối</h3>
        <p>Kiểm tra mã này có giống trên thiết bị của bạn không.</p><strong className={styles.confirmationCode}>{pairing.confirmation}</strong>
        <button type="button" className={styles.primaryButton} disabled={busy} onClick={() => void action("approve")}>Cho phép viết</button>
        <button type="button" className={styles.textButton} disabled={busy} onClick={() => void action("revoke")}>Không phải thiết bị của tôi</button>
      </div> : expired ? <div className={styles.expiredCard}><RefreshCw size={28}/><h3>{pairing.status === "EXPIRED" ? "Mã kết nối đã hết hạn" : "Đã ngắt kết nối"}</h3><p>Tạo mã mới để kết nối thiết bị viết.</p><button type="button" className={styles.primaryButton} disabled={busy} onClick={() => void create()}>Tạo mã mới</button></div>
      : <><div className={styles.qrCard}>{qr ? <img src={qr} alt="Quét mã để kết nối thiết bị viết" width={232} height={232}/> : <LoaderCircle className={styles.spin} size={28}/>}</div>
        <ol className={styles.instructions}><li><span>1</span>Mở camera điện thoại và quét mã.</li><li><span>2</span>Nhấn “Cho phép viết” trên máy tính.</li><li><span>3</span>Bắt đầu viết — không cần đăng nhập lại.</li></ol>
        <p className={styles.expiryNote}>Mã dùng một lần, có hiệu lực trong 2 phút.</p>
        <details className={styles.help}><summary>Không quét được mã?</summary>
          <p>Kết nối điện thoại và máy tính vào cùng mạng Wi-Fi. Nếu vừa đổi mạng, hãy quét mã mới. Mạng khách có thể chặn các thiết bị kết nối với nhau.</p>
          {network?.enabled && network.origin ? <p>Địa chỉ hiện tại: {network.origin}</p> : null}
          {network && !network.enabled && /localhost|127\.0\.0\.1/.test(appOrigin) ? <p>Chưa bật chia sẻ mạng nội bộ. Khởi động dự án với tùy chọn -Lan để điện thoại truy cập được.</p> : null}
          <button type="button" className={styles.secondaryButton} disabled={!link} onClick={async () => {
            try {if (navigator.clipboard) await navigator.clipboard.writeText(link); else {const field = document.createElement("textarea"); field.value = link; document.body.appendChild(field); field.select(); document.execCommand("copy"); field.remove();} setCopied(true);} catch {setError("Chưa sao chép được đường dẫn.");}
          }}><Copy size={15}/>{copied ? "Đã sao chép" : "Sao chép link kết nối"}</button>
          {link ? <a href={link} target="_blank" rel="noreferrer" className={styles.joinLink}>Mở bảng viết trên thiết bị này</a> : null}
        </details>
      </>}
      {error ? <p role="alert" className={styles.error}>{error}<button type="button" className={styles.textButton} onClick={() => void create()}>Thử lại</button></p> : null}
      <p className={styles.privacy}><ShieldCheck size={16}/>Bạn quyết định thiết bị nào được viết vào bài này.</p>
    </div>
  </dialog>;
}
