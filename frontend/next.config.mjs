import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootEnvPath = path.resolve(__dirname, "..", ".env");
const rootEnv = fs.existsSync(rootEnvPath)
  ? Object.fromEntries(
      fs
        .readFileSync(rootEnvPath, "utf8")
        .split(/\r?\n/)
        .filter((line) => line.trim() && !line.trimStart().startsWith("#") && line.includes("="))
        .map((line) => {
          const separator = line.indexOf("=");
          const key = line.slice(0, separator).trim();
          const value = line.slice(separator + 1).trim().replace(/^(?:(['"])(.*)\1)$/, "$2");
          return [key, value];
        })
    )
  : {};

const publicEnv = (name, fallback) => rootEnv[name] ?? process.env[name] ?? fallback;

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_BASE_URL: publicEnv("NEXT_PUBLIC_API_BASE_URL", ""),
    NEXT_PUBLIC_USE_LOCAL_AUTH: publicEnv("NEXT_PUBLIC_USE_LOCAL_AUTH", "true"),
    NEXT_PUBLIC_USE_MOCK_AI: publicEnv("NEXT_PUBLIC_USE_MOCK_AI", "true"),
    SCRAPER_SERVICE_URL: publicEnv("GATEWAY_SCRAPER_SERVICE_URL", "http://localhost:8012")
  }
};

export default nextConfig;
