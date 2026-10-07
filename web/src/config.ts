export const WS_URL: string = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";
export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
/** Voice input socket; defaults to the chat socket's host with /stt. */
export const STT_URL: string = import.meta.env.VITE_STT_URL ?? WS_URL.replace(/\/ws$/, "/stt");
