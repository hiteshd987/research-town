# ── Frontend Dockerfile ───────────────────────────────────────────────────────
# Place this at: frontend/Dockerfile

# Stage 1: Build the Next.js app
# We use a separate build stage so the final image doesn't include
# node_modules, build tools, or source files — only the compiled output
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first (cache layer)
COPY package.json package-lock.json* ./

# Install all dependencies including devDependencies (needed for build)
RUN npm ci

# Copy source code
COPY . .

# Tell Next.js where the backend is during build
ARG NEXT_PUBLIC_API_URL=http://backend:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Build the production Next.js bundle
# This produces the .next/ directory with the compiled app
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────

# Stage 2: Production image — only the built output
FROM node:20-alpine AS runner

WORKDIR /app

# Set production environment
ENV NODE_ENV=production

# Copy only what's needed to RUN the app (not build it)
COPY --from=builder /app/package.json .
COPY --from=builder /app/package-lock.json* .
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public

# Install only production dependencies (no devDeps)
RUN npm ci --only=production

# Expose Next.js port
EXPOSE 3000

# Start Next.js production server
CMD ["npm", "start"]
