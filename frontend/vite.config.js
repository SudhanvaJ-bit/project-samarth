import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The frontend calls the backend directly at VITE_API_URL
// (see src/api/samarth.js), so no dev-server proxy is needed.
// The backend allows this origin through FRONTEND_ORIGINS in its .env.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
})
