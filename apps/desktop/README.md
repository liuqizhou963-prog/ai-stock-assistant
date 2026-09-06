# 股票研究助手桌面版

## 发布安装包

在 `apps/desktop` 目录执行：

```bash
npm install
npm run dist
```

构建脚本会自动创建 `apps/backend/.venv`、安装后端依赖、构建 React 前端，然后由 Electron Builder 生成 Windows 安装包。

安装后的桌面程序会先启动本地 FastAPI 后端，健康检查通过后再打开界面。用户不需要手动启动后端或配置端口。

## 本地开发

先启动 `apps/renderer` 的 Vite 服务，再在 `apps/desktop` 目录执行：

```bash
npm start
```

桌面壳会自动启动后端，并连接到 `http://localhost:5173/`。
