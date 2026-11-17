apiVersion: v1
kind: Namespace
metadata:
  name: enterprise-ai
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-platform
  namespace: enterprise-ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ai-platform
  template:
    metadata:
      labels:
        app: ai-platform
    spec:
      automountServiceAccountToken: false
      containers:
        - name: api
          image: enterprise-ai-platform:0.1.0
          imagePullPolicy: Never
          ports:
            - name: http
              containerPort: 8000
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 500m
              memory: 256Mi
---
apiVersion: v1
kind: Service
metadata:
  name: ai-platform
  namespace: enterprise-ai
spec:
  selector:
    app: ai-platform
  ports:
    - port: 8000
      targetPort: http
