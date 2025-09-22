// 38. src/static/js/xterm-integration.js
/**
 * EulerMaker Docker Optimizer - xterm.js集成脚本
 *
 * ******OSPP-2025-张金荣******
 *
 *  实现与xterm.js的完整集成，提供：
 * - WebSocket终端连接管理
 * - 终端UI控制和交互
 * - 会话状态管理
 * - 快捷键处理
 * - 设置管理和主题切换
 * - 文件管理和监控功能
 * - 命令历史记录
 *
 * @author 张金荣
 * @version 1.0.0
 */

(function(window) {
    'use strict';

    // ====================================
    // 全局变量和常量
    // ====================================
    let terminal = null;
    let websocket = null;
    let fitAddon = null;
    let webLinksAddon = null;
    let searchAddon = null;
    let unicode11Addon = null;

    let isConnected = false;
    let reconnectAttempts = 0;
    let maxReconnectAttempts = 5;
    let reconnectInterval = 5000;
    let reconnectTimer = null;
    let sessionStartTime = null;
    let sessionTimer = null;
    let monitoringTimer = null;

    // 配置对象
    let config = {};
    let settings = {};

    // UI元素引用
    const elements = {};

    // 命令历史
    let commandHistory = [];
    let currentHistoryIndex = -1;

    // 监控数据
    let monitoringData = {
        cpu: [],
        memory: [],
        network: { rx: [], tx: [] }
    };

    // ====================================
    // 初始化函数
    // ====================================
    function init() {
        console.log('EulerMaker Terminal: Initializing...');

        try {
            // 加载配置
            loadConfig();

            // 缓存DOM元素
            cacheElements();

            // 加载设置
            loadSettings();

            // 初始化终端
            initializeTerminal();

            // 绑定事件
            bindEvents();

            // 连接WebSocket
            connect();

            // 显示加载完成
            hideLoading();

            console.log('EulerMaker Terminal: Initialization complete');

        } catch (error) {
            console.error('EulerMaker Terminal: Initialization failed:', error);
            showError('初始化失败: ' + error.message);
        }
    }

    function loadConfig() {
        const configElement = document.getElementById('terminal-config');
        if (configElement) {
            try {
                config = JSON.parse(configElement.textContent);
                console.log('Config loaded:', config);
            } catch (error) {
                console.error('Failed to parse config:', error);
                config = getDefaultConfig();
            }
        } else {
            config = getDefaultConfig();
        }
    }

    function getDefaultConfig() {
        return {
            sessionId: '',
            containerId: '',
            containerName: 'Container',
            websocketUrl: 'ws://localhost:8000/ws/terminals/default',
            terminalWidth: 80,
            terminalHeight: 24,
            apiEndpoint: '/api/v1/terminals',
            enableRecording: true,
            enableMonitoring: true,
            theme: 'dark',
            fontSize: 14,
            fontFamily: 'monospace'
        };
    }

    function cacheElements() {
        const elementIds = [
            'terminal', 'terminal-overlay', 'loading-overlay',
            'connect-btn', 'clear-btn', 'copy-btn', 'paste-btn',
            'settings-btn', 'fullscreen-btn', 'help-btn',
            'connection-status', 'session-time', 'cursor-position',
            'terminal-size', 'network-status', 'cpu-usage', 'memory-usage',
            'side-panel', 'panel-toggle', 'history-list', 'file-list',
            'log-viewer', 'settings-modal', 'help-modal'
        ];

        elementIds.forEach(id => {
            elements[id] = document.getElementById(id);
        });
    }

    function loadSettings() {
        // 从localStorage加载设置
        const savedSettings = localStorage.getItem('eulermaker-terminal-settings');
        if (savedSettings) {
            try {
                settings = JSON.parse(savedSettings);
            } catch (error) {
                console.error('Failed to parse saved settings:', error);
                settings = getDefaultSettings();
            }
        } else {
            settings = getDefaultSettings();
        }

        // 合并配置
        Object.assign(settings, config);
    }

    function getDefaultSettings() {
        return {
            theme: 'dark',
            fontSize: 14,
            fontFamily: 'monospace',
            lineHeight: 1.2,
            cursorBlink: true,
            cursorStyle: 'block',
            bellSound: false,
            scrollOnInput: true,
            fastScroll: true,
            scrollback: 1000,
            opacity: 1.0,
            autoReconnect: true,
            reconnectInterval: 5,
            debugMode: false,
            sessionRecording: true
        };
    }

    // ====================================
    // 终端初始化
    // ====================================
    function initializeTerminal() {
        console.log('Initializing xterm.js terminal...');

        // 创建终端实例
        terminal = new Terminal({
            cursorBlink: settings.cursorBlink,
            cursorStyle: settings.cursorStyle,
            fontSize: settings.fontSize,
            fontFamily: settings.fontFamily,
            lineHeight: settings.lineHeight,
            theme: getTerminalTheme(settings.theme),
            scrollback: settings.scrollback,
            bellSound: settings.bellSound,
            bellStyle: settings.bellSound ? 'sound' : 'none',
            scrollOnUserInput: settings.scrollOnInput,
            fastScrollModifier: settings.fastScroll ? 'alt' : undefined,
            allowTransparency: settings.opacity < 1.0,
            screenReaderMode: false,
            cols: config.terminalWidth || 80,
            rows: config.terminalHeight || 24
        });

        // 加载插件
        fitAddon = new FitAddon.FitAddon();
        webLinksAddon = new WebLinksAddon.WebLinksAddon();
        searchAddon = new SearchAddon.SearchAddon();
        unicode11Addon = new Unicode11Addon.Unicode11Addon();

        // 注册插件
        terminal.loadAddon(fitAddon);
        terminal.loadAddon(webLinksAddon);
        terminal.loadAddon(searchAddon);
        terminal.loadAddon(unicode11Addon);

        // 激活Unicode11支持
        terminal.unicode.activeVersion = '11';

        // 打开终端
        terminal.open(elements.terminal);

        // 适配尺寸
        fitTerminal();

        // 绑定终端事件
        bindTerminalEvents();

        console.log('Terminal initialized successfully');
    }

    function getTerminalTheme(themeName) {
        const themes = {
            dark: {
                foreground: '#ffffff',
                background: '#1e1e1e',
                cursor: '#ffffff',
                cursorAccent: '#000000',
                selection: '#ffffff40',
                black: '#000000',
                red: '#cd3131',
                green: '#0dbc79',
                yellow: '#e5e510',
                blue: '#2472c8',
                magenta: '#bc3fbc',
                cyan: '#11a8cd',
                white: '#e5e5e5',
                brightBlack: '#666666',
                brightRed: '#f14c4c',
                brightGreen: '#23d18b',
                brightYellow: '#f5f543',
                brightBlue: '#3b8eea',
                brightMagenta: '#d670d6',
                brightCyan: '#29b8db',
                brightWhite: '#e5e5e5'
            },
            light: {
                foreground: '#000000',
                background: '#ffffff',
                cursor: '#000000',
                cursorAccent: '#ffffff',
                selection: '#00000040',
                black: '#000000',
                red: '#cd3131',
                green: '#00bc00',
                yellow: '#949800',
                blue: '#0451a5',
                magenta: '#bc05bc',
                cyan: '#0598bc',
                white: '#555555',
                brightBlack: '#666666',
                brightRed: '#cd3131',
                brightGreen: '#14ce14',
                brightYellow: '#b5ba00',
                brightBlue: '#0451a5',
                brightMagenta: '#bc05bc',
                brightCyan: '#0598bc',
                brightWhite: '#a5a5a5'
            }
        };

        return themes[themeName] || themes.dark;
    }

    function bindTerminalEvents() {
        // 数据输入事件
        terminal.onData(data => {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                sendWebSocketMessage('terminal_input', { input: data });

                // 记录命令（简单实现，检测回车）
                if (data === '\r' || data === '\n') {
                    recordCommand();
                }
            }
        });

        // 标题变化事件
        terminal.onTitleChange(title => {
            document.title = `${title} - ${config.containerName} | EulerMaker`;
        });

        // 铃声事件
        terminal.onBell(() => {
            if (settings.bellSound) {
                playBellSound();
            }
        });

        // 选择变化事件
        terminal.onSelectionChange(() => {
            updateCopyButton();
        });

        // 光标位置变化事件
        terminal.onCursorMove(() => {
            updateCursorPosition();
        });

        // 窗口大小变化事件
        window.addEventListener('resize', debounce(fitTerminal, 100));
    }

    function fitTerminal() {
        if (fitAddon && terminal) {
            try {
                fitAddon.fit();

                // 更新尺寸显示
                const { cols, rows } = terminal;
                if (elements['terminal-size']) {
                    elements['terminal-size'].querySelector('span').textContent = `${cols}x${rows}`;
                }

                // 通知服务器终端尺寸变化
                if (websocket && websocket.readyState === WebSocket.OPEN) {
                    sendWebSocketMessage('terminal_resize', {
                        width: cols,
                        height: rows
                    });
                }

            } catch (error) {
                console.error('Failed to fit terminal:', error);
            }
        }
    }

    // ====================================
    // WebSocket连接管理
    // ====================================
    function connect() {
        if (websocket && websocket.readyState === WebSocket.CONNECTING) {
            console.log('WebSocket is already connecting');
            return;
        }

        console.log('Connecting to WebSocket:', config.websocketUrl);
        updateConnectionStatus('connecting', '连接中...');

        try {
            websocket = new WebSocket(config.websocketUrl);

            websocket.onopen = onWebSocketOpen;
            websocket.onmessage = onWebSocketMessage;
            websocket.onclose = onWebSocketClose;
            websocket.onerror = onWebSocketError;

        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            onWebSocketError({ error });
        }
    }

    function disconnect() {
        console.log('Disconnecting WebSocket');

        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }

        if (websocket) {
            websocket.onclose = null; // 防止重连
            websocket.close(1000, 'User disconnected');
            websocket = null;
        }

        isConnected = false;
        updateConnectionStatus('disconnected', '已断开');

        if (elements['connect-btn']) {
            elements['connect-btn'].innerHTML = '<i class="icon-power"></i><span class="btn-text">连接</span>';
        }
    }

    function onWebSocketOpen(event) {
        console.log('WebSocket connected');
        isConnected = true;
        reconnectAttempts = 0;
        sessionStartTime = new Date();

        updateConnectionStatus('connected', '已连接');
        startSessionTimer();

        if (elements['connect-btn']) {
            elements['connect-btn'].innerHTML = '<i class="icon-power"></i><span class="btn-text">断开</span>';
        }

        // 开始监控
        if (config.enableMonitoring) {
            startMonitoring();
        }

        // 发送认证信息（如果需要）
        sendWebSocketMessage('auth', {
            session_id: config.sessionId
        });

        // 聚焦终端
        if (terminal) {
            terminal.focus();
        }
    }

    function onWebSocketMessage(event) {
        try {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
            // 可能是纯文本输出
            if (terminal && event.data) {
                terminal.write(event.data);
            }
        }
    }

    function onWebSocketClose(event) {
        console.log('WebSocket closed:', event.code, event.reason);
        isConnected = false;

        updateConnectionStatus('disconnected', '连接已关闭');
        stopSessionTimer();
        stopMonitoring();

        if (elements['connect-btn']) {
            elements['connect-btn'].innerHTML = '<i class="icon-power"></i><span class="btn-text">连接</span>';
        }

        // 自动重连
        if (settings.autoReconnect && event.code !== 1000) { // 1000 = 正常关闭
            attemptReconnect();
        }
    }

    function onWebSocketError(event) {
        console.error('WebSocket error:', event);
        updateConnectionStatus('error', '连接错误');

        // 显示错误信息
        if (terminal) {
            terminal.writeln('\r\n\x1b[31m连接错误: ' + (event.message || '未知错误') + '\x1b[0m\r\n');
        }
    }

    function attemptReconnect() {
        if (reconnectAttempts >= maxReconnectAttempts) {
            console.log('Max reconnection attempts reached');
            updateConnectionStatus('failed', '连接失败');
            return;
        }

        reconnectAttempts++;
        const delay = reconnectInterval * reconnectAttempts;

        console.log(`Attempting to reconnect in ${delay}ms (attempt ${reconnectAttempts}/${maxReconnectAttempts})`);
        updateConnectionStatus('reconnecting', `重连中... (${reconnectAttempts}/${maxReconnectAttempts})`);

        reconnectTimer = setTimeout(() => {
            connect();
        }, delay);
    }

    function sendWebSocketMessage(type, data) {
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            const message = {
                type: type,
                data: data,
                timestamp: new Date().toISOString()
            };

            websocket.send(JSON.stringify(message));

            if (settings.debugMode) {
                console.log('Sent WebSocket message:', message);
            }
        } else {
            console.warn('WebSocket is not connected, cannot send message:', type, data);
        }
    }

    function handleWebSocketMessage(message) {
        if (settings.debugMode) {
            console.log('Received WebSocket message:', message);
        }

        switch (message.type) {
            case 'terminal_output':
                if (terminal && message.data && message.data.output) {
                    terminal.write(message.data.output);
                }
                break;

            case 'terminal_status':
                handleTerminalStatus(message.data);
                break;

            case 'container_stats':
                updateMonitoringData(message.data);
                break;

            case 'error':
                console.error('Server error:', message.data);
                if (terminal) {
                    terminal.writeln('\r\n\x1b[31m服务器错误: ' + message.data.message + '\x1b[0m\r\n');
                }
                break;

            case 'success':
                console.log('Server success:', message.data);
                break;

            case 'pong':
                // 心跳响应
                break;

            default:
                console.log('Unknown message type:', message.type);
        }
    }

    // ====================================
    // UI事件处理
    // ====================================
    function bindEvents() {
        // 连接按钮
        if (elements['connect-btn']) {
            elements['connect-btn'].addEventListener('click', toggleConnection);
        }

        // 清屏按钮
        if (elements['clear-btn']) {
            elements['clear-btn'].addEventListener('click', clearTerminal);
        }

        // 复制按钮
        if (elements['copy-btn']) {
            elements['copy-btn'].addEventListener('click', copySelection);
        }

        // 粘贴按钮
        if (elements['paste-btn']) {
            elements['paste-btn'].addEventListener('click', pasteFromClipboard);
        }

        // 设置按钮
        if (elements['settings-btn']) {
            elements['settings-btn'].addEventListener('click', showSettings);
        }

        // 全屏按钮
        if (elements['fullscreen-btn']) {
            elements['fullscreen-btn'].addEventListener('click', toggleFullscreen);
        }

        // 帮助按钮
        if (elements['help-btn']) {
            elements['help-btn'].addEventListener('click', showHelp);
        }

        // 面板切换按钮
        if (elements['panel-toggle']) {
            elements['panel-toggle'].addEventListener('click', toggleSidePanel);
        }

        // 键盘事件
        document.addEventListener('keydown', handleKeyboardShortcuts);

        // 标签页切换
        bindTabEvents();

        // 设置对话框事件
        bindSettingsEvents();

        // 帮助对话框事件
        bindHelpEvents();

        // 面板标签事件
        bindPanelTabEvents();
    }

    function toggleConnection() {
        if (isConnected) {
            disconnect();
        } else {
            connect();
        }
    }

    function clearTerminal() {
        if (terminal) {
            terminal.clear();
            terminal.write('\x1b[2J\x1b[H'); // 清屏并移动光标到左上角
        }
    }

    function copySelection() {
        if (terminal && terminal.hasSelection()) {
            const selection = terminal.getSelection();
            navigator.clipboard.writeText(selection).then(() => {
                showNotification('已复制到剪贴板');
            }).catch(error => {
                console.error('Failed to copy to clipboard:', error);
                // 降级方案
                fallbackCopyToClipboard(selection);
            });
        }
    }

    function pasteFromClipboard() {
        navigator.clipboard.readText().then(text => {
            if (terminal && text) {
                // 发送粘贴的文本到终端
                sendWebSocketMessage('terminal_input', { input: text });
            }
        }).catch(error => {
            console.error('Failed to read from clipboard:', error);
            showNotification('无法从剪贴板读取内容');
        });
    }

    function toggleFullscreen() {
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else {
            document.documentElement.requestFullscreen();
        }
    }

    function toggleSidePanel() {
        const panel = elements['side-panel'];
        if (panel) {
            panel.classList.toggle('hidden');

            // 重新适配终端尺寸
            setTimeout(fitTerminal, 300);
        }
    }

    function handleKeyboardShortcuts(event) {
        // Ctrl+Shift+C - 复制
        if (event.ctrlKey && event.shiftKey && event.code === 'KeyC') {
            event.preventDefault();
            copySelection();
            return;
        }

        // Ctrl+Shift+V - 粘贴
        if (event.ctrlKey && event.shiftKey && event.code === 'KeyV') {
            event.preventDefault();
            pasteFromClipboard();
            return;
        }

        // Ctrl+L - 清屏
        if (event.ctrlKey && event.code === 'KeyL') {
            event.preventDefault();
            clearTerminal();
            return;
        }

        // F11 - 全屏
        if (event.code === 'F11') {
            event.preventDefault();
            toggleFullscreen();
            return;
        }

        // Ctrl+, - 设置
        if (event.ctrlKey && event.code === 'Comma') {
            event.preventDefault();
            showSettings();
            return;
        }

        // F1 - 帮助
        if (event.code === 'F1') {
            event.preventDefault();
            showHelp();
            return;
        }

        // Escape - 关闭对话框
        if (event.code === 'Escape') {
            closeModals();
            return;
        }
    }

    // ====================================
    // 状态管理
    // ====================================
    function updateConnectionStatus(status, message) {
        const statusElement = elements['connection-status'];
        if (statusElement) {
            statusElement.textContent = message;
            statusElement.className = `badge-status status-${status}`;
        }

        const networkIcon = document.getElementById('network-icon');
        const networkStatus = document.getElementById('network-status');

        if (networkIcon && networkStatus) {
            networkIcon.className = `icon-network status-${status}`;
            networkStatus.textContent = message;
        }
    }

    function startSessionTimer() {
        sessionTimer = setInterval(() => {
            if (sessionStartTime) {
                const elapsed = Date.now() - sessionStartTime.getTime();
                const duration = formatDuration(elapsed);

                const timeElement = elements['session-time'];
                if (timeElement) {
                    timeElement.textContent = `连接时间: ${duration}`;
                }
            }
        }, 1000);
    }

    function stopSessionTimer() {
        if (sessionTimer) {
            clearInterval(sessionTimer);
            sessionTimer = null;
        }
    }

    function updateCursorPosition() {
        const positionElement = elements['cursor-position'];
        if (positionElement && terminal) {
            const buffer = terminal.buffer.active;
            positionElement.querySelector('span').textContent =
                `行: ${buffer.cursorY + 1}, 列: ${buffer.cursorX + 1}`;
        }
    }

    function updateCopyButton() {
        const copyBtn = elements['copy-btn'];
        if (copyBtn) {
            if (terminal && terminal.hasSelection()) {
                copyBtn.disabled = false;
                copyBtn.classList.add('has-selection');
            } else {
                copyBtn.disabled = true;
                copyBtn.classList.remove('has-selection');
            }
        }
    }

    // ====================================
    // 监控功能
    // ====================================
    function startMonitoring() {
        if (!config.enableMonitoring) return;

        monitoringTimer = setInterval(() => {
            requestContainerStats();
        }, 5000); // 每5秒更新一次
    }

    function stopMonitoring() {
        if (monitoringTimer) {
            clearInterval(monitoringTimer);
            monitoringTimer = null;
        }
    }

    function requestContainerStats() {
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            sendWebSocketMessage('request_stats', {
                container_id: config.containerId
            });
        }
    }

    function updateMonitoringData(stats) {
        if (!stats) return;

        // 更新状态栏
        const cpuElement = document.getElementById('cpu-usage');
        const memoryElement = document.getElementById('memory-usage');

        if (cpuElement) {
            cpuElement.textContent = `${stats.cpu_usage.toFixed(1)}%`;
        }

        if (memoryElement) {
            const memoryPercent = (stats.memory_usage / stats.memory_limit) * 100;
            memoryElement.textContent = `${memoryPercent.toFixed(1)}%`;
        }

        // 更新监控图表数据
        const now = Date.now();
        monitoringData.cpu.push({ time: now, value: stats.cpu_usage });
        monitoringData.memory.push({ time: now, value: memoryPercent });

        // 限制数据点数量
        const maxDataPoints = 60; // 保留5分钟的数据（每5秒一个点）
        if (monitoringData.cpu.length > maxDataPoints) {
            monitoringData.cpu.shift();
        }
        if (monitoringData.memory.length > maxDataPoints) {
            monitoringData.memory.shift();
        }

        // 更新图表显示
        updateMonitoringCharts();
    }

    function updateMonitoringCharts() {
        // 这里可以集成图表库（如Chart.js）来显示监控数据
        // 目前只是一个简单的实现
        updateSimpleChart('cpu-chart', monitoringData.cpu, 'CPU使用率');
        updateSimpleChart('memory-chart', monitoringData.memory, '内存使用率');
    }

    function updateSimpleChart(chartId, data, label) {
        const chartElement = document.getElementById(chartId);
        if (!chartElement || data.length === 0) return;

        const placeholder = chartElement.querySelector('.chart-placeholder');
        if (placeholder) {
            const latestValue = data[data.length - 1].value;
            placeholder.textContent = `${label}: ${latestValue.toFixed(1)}%`;

            // 添加简单的颜色指示
            placeholder.className = 'chart-placeholder';
            if (latestValue > 80) {
                placeholder.classList.add('high');
            } else if (latestValue > 60) {
                placeholder.classList.add('medium');
            } else {
                placeholder.classList.add('low');
            }
        }
    }

    // ====================================
    // 命令历史管理
    // ====================================
    function recordCommand() {
        // 简单的命令记录实现
        // 实际应用中应该从服务器获取完整的命令信息
        const buffer = terminal.buffer.active;
        const currentLine = buffer.getLine(buffer.cursorY);

        if (currentLine) {
            let command = '';
            for (let i = 0; i < currentLine.length; i++) {
                const cell = currentLine.getCell(i);
                if (cell) {
                    command += cell.getChars();
                }
            }

            command = command.trim();
            if (command && command !== commandHistory[commandHistory.length - 1]) {
                commandHistory.push({
                    command: command,
                    timestamp: new Date().toISOString(),
                    exitCode: null
                });

                // 限制历史记录数量
                if (commandHistory.length > 1000) {
                    commandHistory.shift();
                }

                // 更新历史面板
                updateHistoryPanel();
            }
        }
    }

    function updateHistoryPanel() {
        const historyList = elements['history-list'];
        if (!historyList) return;

        historyList.innerHTML = '';

        if (commandHistory.length === 0) {
            historyList.innerHTML = `
                <div class="empty-state">
                    <i class="icon-history-empty"></i>
                    <p>暂无命令历史</p>
                </div>
            `;
            return;
        }

        // 显示最近的命令（倒序）
        const recentCommands = commandHistory.slice(-50).reverse();

        recentCommands.forEach((entry, index) => {
            const item = document.createElement('div');
            item.className = 'history-item';
            item.innerHTML = `
                <div class="history-command">${escapeHtml(entry.command)}</div>
                <div class="history-time">${formatTime(entry.timestamp)}</div>
            `;

            item.addEventListener('click', () => {
                // 点击历史命令时将其发送到终端
                if (terminal && isConnected) {
                    sendWebSocketMessage('terminal_input', { input: entry.command + '\r' });
                }
            });

            historyList.appendChild(item);
        });
    }

    // ====================================
    // 设置管理
    // ====================================
    function showSettings() {
        const modal = elements['settings-modal'];
        if (modal) {
            modal.classList.add('show');
            loadSettingsValues();
        }
    }

    function hideSettings() {
        const modal = elements['settings-modal'];
        if (modal) {
            modal.classList.remove('show');
        }
    }

    function loadSettingsValues() {
        // 加载当前设置值到设置对话框
        const themeSelect = document.getElementById('theme-select');
        if (themeSelect) themeSelect.value = settings.theme;

        const fontFamilySelect = document.getElementById('font-family-select');
        if (fontFamilySelect) fontFamilySelect.value = settings.fontFamily;

        const fontSizeRange = document.getElementById('font-size-range');
        if (fontSizeRange) {
            fontSizeRange.value = settings.fontSize;
            fontSizeRange.nextElementSibling.textContent = settings.fontSize + 'px';
        }

        // 加载其他设置...
    }

    function saveSettings() {
        // 从设置对话框保存设置值
        const themeSelect = document.getElementById('theme-select');
        if (themeSelect) settings.theme = themeSelect.value;

        const fontFamilySelect = document.getElementById('font-family-select');
        if (fontFamilySelect) settings.fontFamily = fontFamilySelect.value;

        const fontSizeRange = document.getElementById('font-size-range');
        if (fontSizeRange) settings.fontSize = parseInt(fontSizeRange.value);

        // 保存其他设置...

        // 保存到localStorage
        localStorage.setItem('eulermaker-terminal-settings', JSON.stringify(settings));

        // 应用设置
        applySettings();

        // 关闭设置对话框
        hideSettings();

        showNotification('设置已保存');
    }

    function applySettings() {
        if (terminal) {
            // 应用主题
            terminal.options.theme = getTerminalTheme(settings.theme);

            // 应用字体设置
            terminal.options.fontSize = settings.fontSize;
            terminal.options.fontFamily = settings.fontFamily;
            terminal.options.lineHeight = settings.lineHeight;

            // 应用其他设置
            terminal.options.cursorBlink = settings.cursorBlink;
            terminal.options.scrollback = settings.scrollback;

            // 刷新终端
            terminal.refresh(0, terminal.rows - 1);
        }

        // 应用透明度
        if (elements.terminal) {
            elements.terminal.style.opacity = settings.opacity;
        }
    }

    function bindSettingsEvents() {
        // 设置对话框事件绑定
        const closeBtn = document.getElementById('settings-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', hideSettings);
        }

        const saveBtn = document.getElementById('settings-save-btn');
        if (saveBtn) {
            saveBtn.addEventListener('click', saveSettings);
        }

        const resetBtn = document.getElementById('settings-reset-btn');
        if (resetBtn) {
            resetBtn.addEventListener('click', resetSettings);
        }

        // 设置标签页切换
        const settingsTabs = document.querySelectorAll('.settings-tab');
        settingsTabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                const tabName = e.target.dataset.tab;
                switchSettingsTab(tabName);
            });
        });

        // 范围滑块事件
        const ranges = document.querySelectorAll('.setting-range');
        ranges.forEach(range => {
            range.addEventListener('input', (e) => {
                const valueSpan = e.target.nextElementSibling;
                if (valueSpan) {
                    let value = e.target.value;
                    if (e.target.id === 'opacity-range') {
                        value = Math.round(value * 100) + '%';
                    } else if (e.target.id === 'font-size-range') {
                        value = value + 'px';
                    }
                    valueSpan.textContent = value;
                }
            });
        });
    }

    // ====================================
    // 工具函数
    // ====================================
    function showLoading() {
        const overlay = elements['loading-overlay'];
        if (overlay) {
            overlay.classList.add('show');
        }
    }

    function hideLoading() {
        const overlay = elements['loading-overlay'];
        if (overlay) {
            overlay.classList.remove('show');
        }
    }

    function showError(message) {
        const overlay = elements['terminal-overlay'];
        if (overlay) {
            overlay.querySelector('.overlay-message').textContent = message;
            overlay.classList.remove('hidden');
        }
    }

    function hideError() {
        const overlay = elements['terminal-overlay'];
        if (overlay) {
            overlay.classList.add('hidden');
        }
    }

    function showNotification(message, type = 'info', duration = 3000) {
        // 创建通知元素
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <i class="notification-icon"></i>
                <span class="notification-message">${message}</span>
            </div>
        `;

        document.body.appendChild(notification);

        // 显示动画
        setTimeout(() => notification.classList.add('show'), 10);

        // 自动隐藏
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, duration);
    }

    function formatDuration(ms) {
        const seconds = Math.floor(ms / 1000);
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        } else {
            return `${minutes}:${secs.toString().padStart(2, '0')}`;
        }
    }

    function formatTime(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('zh-CN', { hour12: false });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    function fallbackCopyToClipboard(text) {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();

        try {
            const successful = document.execCommand('copy');
            if (successful) {
                showNotification('已复制到剪贴板');
            }
        } catch (err) {
            console.error('Fallback copy failed:', err);
        }

        document.body.removeChild(textArea);
    }

    function playBellSound() {
        // 播放铃声
        const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N+TQAoUXrTp66hVFApGn+DyvmAZAjiL0fLNdSUEIXOz7eCWRAoRVK3n77BdGAU7k9nyyHkpBCJ+w+9tOgAAUKMM');
        audio.volume = 0.1;
        audio.play().catch(e => console.log('Could not play bell sound:', e));
    }

    function closeModals() {
        hideSettings();
        hideHelp();
    }

    function showHelp() {
        const modal = elements['help-modal'];
        if (modal) {
            modal.classList.add('show');
        }
    }

    function hideHelp() {
        const modal = elements['help-modal'];
        if (modal) {
            modal.classList.remove('show');
        }
    }

    function bindHelpEvents() {
        const closeBtn = document.getElementById('help-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', hideHelp);
        }

        const okBtn = document.getElementById('help-ok-btn');
        if (okBtn) {
            okBtn.addEventListener('click', hideHelp);
        }
    }

    function bindTabEvents() {
        // 主标签页事件绑定占位符
    }

    function bindPanelTabEvents() {
        const tabButtons = document.querySelectorAll('.tab-btn');
        tabButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tabName = e.currentTarget.dataset.tab;
                switchPanelTab(tabName);
            });
        });
    }

    function switchPanelTab(tabName) {
        // 切换活跃标签
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

        // 切换内容面板
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.remove('active');
        });
        document.getElementById(`${tabName}-pane`).classList.add('active');
    }

    function switchSettingsTab(tabName) {
        // 切换设置标签
        document.querySelectorAll('.settings-tab').forEach(tab => {
            tab.classList.remove('active');
        });
        document.querySelector(`.settings-tab[data-tab="${tabName}"]`).classList.add('active');

        // 切换设置面板
        document.querySelectorAll('.settings-pane').forEach(pane => {
            pane.classList.remove('active');
        });
        document.getElementById(`${tabName}-settings`).classList.add('active');
    }

    function resetSettings() {
        if (confirm('确定要重置所有设置吗？这将恢复默认配置。')) {
            settings = getDefaultSettings();
            localStorage.removeItem('eulermaker-terminal-settings');
            loadSettingsValues();
            applySettings();
            showNotification('设置已重置');
        }
    }

    // ====================================
    // 页面加载完成后初始化
    // ====================================
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // 导出API到全局对象（用于调试）
    window.EulerMakerTerminal = {
        terminal,
        websocket,
        config,
        settings,
        connect,
        disconnect,
        clearTerminal,
        fitTerminal,
        showSettings,
        showHelp
    };

})(window);