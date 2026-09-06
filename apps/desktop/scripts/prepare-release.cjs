const { existsSync, cpSync, rmSync, mkdirSync } = require('node:fs')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

const desktopDirectory = path.resolve(__dirname, '..')
const rendererDirectory = path.resolve(desktopDirectory, '../renderer')
const backendDirectory = path.resolve(desktopDirectory, '../backend')
const newsServiceDirectory = path.resolve(desktopDirectory, '../news-service')
const requirementsFile = path.join(backendDirectory, 'requirements.txt')
const newsRequirementsFile = path.join(newsServiceDirectory, 'requirements.txt')
const virtualEnvironmentDirectory = path.join(backendDirectory, '.venv')
const newsVirtualEnvironmentDirectory = path.join(newsServiceDirectory, '.venv')
const piRuntimeDirectory = path.resolve(desktopDirectory, '../pi-runtime')

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    stdio: 'inherit',
    shell: process.platform === 'win32' && command.toLowerCase().endsWith('.cmd'),
  })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`${command} ${args.join(' ')} 执行失败，退出码 ${result.status}`)
}

function findPython() {
  const candidates = process.platform === 'win32'
    ? [['py', ['-3']], ['python', []]]
    : [['python3', []], ['python', []]]

  for (const [command, args] of candidates) {
    const result = spawnSync(command, [...args, '--version'], { stdio: 'ignore', shell: false })
    if (!result.error && result.status === 0) return [command, args]
  }
  throw new Error('未找到 Python 3。请先安装 Python 3.10 或更高版本，并确保命令可用。')
}

function virtualEnvironmentPython(directory) {
  return process.platform === 'win32'
    ? path.join(directory, 'Scripts', 'python.exe')
    : path.join(directory, 'bin', 'python')
}

function prepareVirtualEnvironment(directory, requirements, label, cwd) {
  const environmentPython = virtualEnvironmentPython(directory)
  if (!existsSync(environmentPython)) {
    console.log(`正在创建${label} Python 虚拟环境...`)
    run(pythonCommand, [...pythonPrefixArgs, '-m', 'venv', directory], desktopDirectory)
  }
  console.log(`正在安装${label}依赖...`)
  run(environmentPython, ['-m', 'pip', 'install', '-r', requirements], cwd)
}

const [pythonCommand, pythonPrefixArgs] = findPython()
prepareVirtualEnvironment(virtualEnvironmentDirectory, requirementsFile, '后端', backendDirectory)
prepareVirtualEnvironment(newsVirtualEnvironmentDirectory, newsRequirementsFile, '资讯服务', newsServiceDirectory)

console.log('正在构建前端...')
run(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['run', 'build'], rendererDirectory)

console.log('正在构建 Pi Runtime...')
run(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['install'], piRuntimeDirectory)
run(process.platform === 'win32' ? 'npx.cmd' : 'npx', ['esbuild', 'src/server.mjs', '--bundle', '--platform=node', '--format=esm', '--external:yaml', '--outfile=dist/server.bundle.mjs'], piRuntimeDirectory)
const piVendorDirectory = path.resolve(desktopDirectory, '../../vendor/pi')
const piRuntimeNodeModules = path.join(piRuntimeDirectory, 'node_modules')
rmSync(piRuntimeNodeModules, { recursive: true, force: true })
mkdirSync(piRuntimeNodeModules, { recursive: true })
cpSync(path.join(piVendorDirectory, 'node_modules'), piRuntimeNodeModules, { recursive: true })
cpSync(path.join(piVendorDirectory, 'node_modules', 'yaml'), path.join(piRuntimeNodeModules, 'yaml'), { recursive: true })
mkdirSync(path.join(piRuntimeNodeModules, '@earendil-works'), { recursive: true })
for (const packageName of ['agent', 'ai', 'chord', 'telemetry']) {
  const runtimeName = packageName === 'agent' ? 'pi-agent-core' : `pi-${packageName}`
  cpSync(path.join(piVendorDirectory, 'packages', packageName), path.join(piRuntimeNodeModules, '@earendil-works', runtimeName), { recursive: true })
}

console.log('桌面端发布资源准备完成。')
