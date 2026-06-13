import { defineConfig } from 'vite';

export default defineConfig({
    base: './', // Use relative path for safer deployment
    build: {
        outDir: 'dist',
    }
});
