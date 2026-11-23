// PM2 - VEILLE sur le VPS (une seule instance : le planificateur ne doit tourner qu'une fois)
const port = process.env.VEILLE_PORT || '5727';
module.exports = {
  apps: [{
    name: 'veille',
    cwd: './backend',
    script: '.venv/bin/uvicorn',
    args: `app.main:app --host 127.0.0.1 --port ${port} --proxy-headers --forwarded-allow-ips 127.0.0.1`,
    interpreter: 'none',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '400M',
    env: { VEILLE_PORT: port, PYTHONUNBUFFERED: '1' },
    time: true,
  }],
};
