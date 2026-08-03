import axios from "axios";

// The Gateway. With no fallback this was `undefined`, which axios treats as
// "same origin" — so every auth call went to the Next.js server instead of the
// API and 404'd, with nothing to indicate a missing environment variable
// (BUG-045). Copy .env.example to .env.local to point at anything else.
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080",
  withCredentials: true,
});

export default api;
