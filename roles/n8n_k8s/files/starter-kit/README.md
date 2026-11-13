# Vendored self-hosted-ai-starter-kit demo data

Source: https://github.com/n8n-io/self-hosted-ai-starter-kit
Upstream revision: `662bd8892476b41d9084417a569cc84013354674`
Local working checkout this was taken from: `~/tools/self-hosted-ai-starter-kit`

These assets are vendored so the Kubernetes deployment is reproducible from this
repository alone. The role must not depend on a developer's home-directory
checkout being present on the target.

## workflows/

`srOnR8PAY3u4RSwb.json` is upstream's "Demo workflow", byte-for-byte. It
references the Ollama credential by id `xHuYe0MDGOs9IpBW` and asks for model
`llama3.2:latest`, which is what `ollama pull llama3.2` produces.

## credentials/

**Re-authored, not copied.** Upstream ships these two credentials with their
`data` field already encrypted with the starter kit's demo
`N8N_ENCRYPTION_KEY` (`super-secret-key` from its `.env.example`). This
deployment takes its encryption key from Bitwarden Secrets Manager instead, so
upstream's ciphertext is undecryptable here — importing it verbatim produces
two credentials that exist in the UI but fail every request.

The files therefore carry `data` as a **plaintext object**. `n8n import:credentials`
treats an object-valued `data` as cleartext and encrypts it with the running
instance's own key:

```js
// dist/commands/import/credentials.js (n8n 2.47.5)
const isCredentialData = (data) => typeof data === 'object' && data !== null && !Array.isArray(data);
...
if (isCredentialData(filteredCredential.data)) {
    filteredCredential.data = await cipher.encryptV2(filteredCredential.data);
}
```

The upstream credential **ids and names are preserved** so the demo workflow's
credential references resolve without editing the workflow.

Hostnames (`http://ollama:11434`, `http://qdrant:6333`) are the in-namespace
Kubernetes Services the role creates, which are deliberately named `ollama` and
`qdrant` to match upstream's Compose service names.

Property names were read from the running image rather than assumed:

- `ollamaApi` -> `baseUrl`, `apiKey` (`dist/credentials/OllamaApi.credentials.js`)
- `qdrantApi` -> `qdrantUrl`, `apiKey` (`dist/credentials/QdrantApi.credentials.js`)

## What is deliberately NOT vendored

`docker-compose.yml` and `.env` are upstream's Compose path. The Kubernetes
path renders the equivalent workloads as Helm `extraObjects` in the n8n release;
see `roles/n8n_k8s/templates/starter-kit-objects.yml.j2`.
