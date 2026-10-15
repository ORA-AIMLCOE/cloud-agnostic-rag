FROM node:20-bookworm AS node
FROM python:3.11-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && useradd -u 1000 -m validator
COPY backend.lock.txt /opt/backend.lock.txt
RUN pip install --no-cache-dir -r /opt/backend.lock.txt
WORKDIR /opt/frontend
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY run.py /opt/run.py
USER validator
WORKDIR /tmp
ENTRYPOINT ["python", "/opt/run.py"]
