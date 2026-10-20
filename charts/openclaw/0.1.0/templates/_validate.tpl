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
{{- if ne .Values.image.tag "2026.10.5" -}}
{{- fail "image.tag must remain on verified release 2026.10.5" -}}
{{- end -}}
{{- if ne .Values.image.digest "sha256:f40d1e66fd14d8c5b49c832f4100f83b53fdc01f5108f7db11de38fd0ee6dbe5" -}}
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
{{- if not (has (printf "https://%s" .Values.ingress.host) .Values.gateway.allowedOrigins) -}}
{{- fail "gateway.allowedOrigins must include the exact HTTPS Ingress origin" -}}
{{- end -}}
{{- else if ne .Values.gateway.bind "loopback" -}}
{{- fail "gateway.bind must be loopback when exposure is disabled" -}}
{{- end -}}
{{- end -}}
