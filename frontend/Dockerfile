# Dashboard image. Build from the REPO ROOT context (npm workspaces need the
# root manifest + packages/), e.g.:
#   docker build -f frontend/Dockerfile .
# Layer order matters: manifests first so the install layer only busts when a
# manifest changes, not on every source edit (community PR TsukumoHQ/yoru#7).
#
# Stage 1: build the React application
FROM node:20-alpine AS builder

WORKDIR /app

# Manifests only — the install layer caches across source-only changes.
COPY package.json package-lock.json ./
COPY packages/receipt-ui/package.json ./packages/receipt-ui/
COPY frontend/package.json ./frontend/

# The public mirror strips the private marketing/ workspace while the dev
# monorepo lists it — drop any workspace whose manifest isn't in this build
# context so ONE Dockerfile works against both trees. (`npm install` rather
# than `npm ci`: the dev tree's lockfile still carries the pruned workspace;
# install resolves the remaining deps from the locked versions.)
RUN node -e "const fs=require('fs');const p=JSON.parse(fs.readFileSync('package.json','utf8'));p.workspaces=(p.workspaces||[]).filter(w=>w.includes('*')||fs.existsSync(w+'/package.json'));fs.writeFileSync('package.json',JSON.stringify(p,null,2)+'\n')" \
    && npm install --no-audit --no-fund

# Source after install — source changes rebuild, not reinstall.
COPY packages ./packages
COPY frontend ./frontend
RUN npm run build --workspace frontend

# Stage 2: serve with nginx
FROM nginx:alpine

COPY --from=builder /app/frontend/dist /usr/share/nginx/html
COPY --from=builder /app/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
