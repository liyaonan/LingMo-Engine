import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['tests/**/*.test.js'],
  },
  resolve: {
    alias: [
      // 插件前端文件已迁移到各插件 static/frontend-v2/ 目录
      { find: '/static/plugins/combat/frontend-v2', replacement: __dirname + '/../../../plugins/combat/static/frontend-v2' },
      { find: '/static/plugins/inventory/frontend-v2', replacement: __dirname + '/../../../plugins/inventory/static/frontend-v2' },
      { find: '/static/plugins/event/frontend-v2', replacement: __dirname + '/../../../plugins/event/static/frontend-v2' },
      { find: '/static/plugins/character/frontend-v2', replacement: __dirname + '/../../../plugins/character/static/frontend-v2' },
      // 核心前端文件自身引用
      { find: '/static/frontend-v2', replacement: __dirname },
    ],
  },
});
