// frontend/next.config.js
// Place this at: frontend/next.config.js
//
// WHY THIS EXISTS:
//   In Docker, the frontend container cannot reach "localhost:8000" because
//   localhost inside a container means the container itself, not the host machine.
//   Containers reach each other by service name: "http://backend:8000"
//
//   But we don't want to change every fetch() call in page.tsx.
//   Instead, we use Next.js rewrites:
//     - Browser calls:    /api/*  → Next.js proxies to backend:8000/api/*
//     - This works both in Docker (service name) and locally (localhost)
//
//   Set NEXT_PUBLIC_API_URL in docker-compose.yml for Docker,
//   it defaults to localhost:8000 for local development.

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
