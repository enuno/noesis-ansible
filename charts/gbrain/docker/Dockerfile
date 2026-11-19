# First-party runtime image for k3s. Upstream publishes no production image.
# Built from a garrytan/gbrain checkout (default ~/tools/gbrain).
ARG BUN_IMAGE=oven/bun:1.4.4
FROM ${BUN_IMAGE}

WORKDIR /app
COPY package.json bun.lock bunfig.toml ./
COPY patches/ patches/
RUN bun install --frozen-lockfile
COPY . .
RUN mkdir -p /var/lib/gbrain && chown -R 1000:1000 /app /var/lib/gbrain

USER 1000
ENV GBRAIN_HOME=/var/lib/gbrain
EXPOSE 3131
ENTRYPOINT ["bun", "run", "src/cli.ts"]
CMD ["serve", "--http", "--port", "3131", "--bind", "0.0.0.0"]
