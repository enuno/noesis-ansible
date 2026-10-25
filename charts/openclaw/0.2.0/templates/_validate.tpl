{{- define "openclaw.validate" -}}
{{- if ne (int .Values.replicaCount) 1 -}}
{{- fail "replicaCount must be 1 for single-writer OpenClaw state" -}}
{{- end -}}
{{- if ne .Values.strategy "Recreate" -}}
{{- fail "strategy must be Recreate" -}}
{{- end -}}
{{- if not .Values.existingSecret -}}
{{- fail "existingSecret is required; this chart never creates a Secret" -}}
{{- end -}}
{{- if ne .Values.image.repository "ghcr.io/openclaw/openclaw" -}}
{{- fail "image.repository must remain ghcr.io/openclaw/openclaw" -}}
{{- end -}}
{{- if ne .Values.image.tag "2026.10.7-slim" -}}
{{- fail "image.tag must remain on verified release 2026.10.7-slim" -}}
{{- end -}}
{{- if ne .Values.image.digest "sha256:fb26f0841659dc757f23feec9adeab51f11d76779a409db5d22e191b43841afa" -}}
{{- fail "image.digest must remain on the verified multi-architecture OCI index" -}}
{{- end -}}
{{- if ne .Values.service.type "ClusterIP" -}}
{{- fail "service.type must be ClusterIP" -}}
{{- end -}}
{{- if ne (int .Values.service.port) 18789 -}}
{{- fail "service.port must be 18789" -}}
{{- end -}}
{{- if ne .Values.gateway.authMode "token" -}}
{{- fail "gateway.authMode must be token" -}}
{{- end -}}
{{- if .Values.gateway.externalMessagingEnabled -}}
{{- fail "external messaging is outside this chart's authority" -}}
{{- end -}}
{{- if not .Values.persistence.enabled -}}
{{- fail "persistent single-writer state must remain enabled" -}}
{{- end -}}
{{- if .Values.ingress.enabled -}}
{{- if ne .Values.ingress.className "tailscale" -}}
{{- fail "only the tailscale IngressClass is supported" -}}
{{- end -}}
{{- if ne .Values.gateway.bind "lan" -}}
{{- fail "gateway.bind must be lan when Tailscale Ingress is enabled" -}}
{{- end -}}
{{- if not .Values.ingress.host -}}
{{- fail "ingress.host is required when exposure is enabled" -}}
{{- end -}}
{{- if not .Values.ingress.tailnetDomain -}}
{{- fail "ingress.tailnetDomain is required when exposure is enabled; the Control UI validates the browser's real origin https://<host>.<tailnetDomain>" -}}
{{- end -}}
{{- if contains "." .Values.ingress.host -}}
{{- fail "ingress.host must be a bare hostspec (e.g. noesis-openclaw); the Tailscale operator appends the tailnet domain itself" -}}
{{- end -}}
{{- if has .Values.ingress.host .Values.ingress.reservedHostnames -}}
{{- fail (printf "ingress.host %q is reserved; claiming it would hijack that device's identity" .Values.ingress.host) -}}
{{- end -}}
{{- $origin := printf "https://%s.%s" .Values.ingress.host .Values.ingress.tailnetDomain -}}
{{- if not (has $origin .Values.gateway.allowedOrigins) -}}
{{- fail (printf "gateway.allowedOrigins must include the exact browser origin %s" $origin) -}}
{{- end -}}
{{- else if ne .Values.gateway.bind "loopback" -}}
{{- fail "gateway.bind must be loopback when exposure is disabled" -}}
{{- end -}}
{{- end -}}
