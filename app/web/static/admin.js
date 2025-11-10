// Admin panel JavaScript

// API base URL
const API_BASE = '';

// API Key management
function getApiKey() {
    return localStorage.getItem('admin_api_key');
}

function setApiKey(key) {
    localStorage.setItem('admin_api_key', key);
}

function clearApiKey() {
    if (confirm('确定要清除 API 密钥吗？')) {
        localStorage.removeItem('admin_api_key');
        promptForApiKey();
    }
}

function promptForApiKey() {
    // 重定向到登录页面
    window.location.href = '/admin/login';
}

// Make authenticated request
async function fetchWithAuth(url, options = {}) {
    const apiKey = getApiKey();
    if (!apiKey) {
        // 重定向到登录页面
        window.location.href = '/admin/login';
        throw new Error('No API key');
    }
    
    const headers = {
        ...options.headers,
        'Authorization': `Bearer ${apiKey}`
    };
    
    const response = await fetch(url, { ...options, headers });
    
    // Handle auth errors
    if (response.status === 401 || response.status === 403) {
        clearApiKey();
        // 重定向到登录页面
        window.location.href = '/admin/login';
        throw new Error('Authentication failed');
    }
    
    return response;
}

// Handle authentication errors
function handleAuthError(error) {
    if (error.message && (error.message.includes('401') || error.message.includes('403'))) {
        clearApiKey();
        return true;
    }
    return false;
}

// Show/hide sections
function showSection(section) {
    // Hide all sections
    document.querySelectorAll('.section').forEach(el => {
        el.style.display = 'none';
    });
    
    // Update nav links
    document.querySelectorAll('.nav-link').forEach(el => {
        el.classList.remove('active');
    });
    
    // Show selected section
    document.getElementById(`${section}-section`).style.display = 'block';
    event.target.classList.add('active');
    
    // Load data for section
    if (section === 'dashboard') {
        loadDashboard();
    } else if (section === 'accounts') {
        loadAccounts();
    } else if (section === 'apikeys') {
        loadApiKeys();
    }
}

// Chart instance
let tokensChart = null;

// Format number with commas
function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// Format large numbers (K, M, B)
function formatLargeNumber(num) {
    if (num === null || num === undefined) return '0';
    if (num >= 1000000000) {
        return (num / 1000000000).toFixed(2) + 'B';
    }
    if (num >= 1000000) {
        return (num / 1000000).toFixed(2) + 'M';
    }
    if (num >= 1000) {
        return (num / 1000).toFixed(2) + 'K';
    }
    return num.toString();
}

// Load dashboard stats
async function loadDashboard() {
    try {
        const [accountStats, keyStats, tokensStats, accountUsageStats] = await Promise.all([
            fetchWithAuth(`${API_BASE}/admin/stats/accounts`).then(r => r.json()),
            fetchWithAuth(`${API_BASE}/admin/stats/api-keys`).then(r => r.json()),
            fetchWithAuth(`${API_BASE}/admin/stats/tokens?days=7`).then(r => r.json()),
            fetchWithAuth(`${API_BASE}/admin/stats/account-usage?days=7`).then(r => r.json())
        ]);
        
        // Update basic stats
        document.getElementById('total-accounts').textContent = accountStats.total_accounts;
        document.getElementById('active-accounts').textContent = accountStats.active_accounts;
        document.getElementById('total-keys').textContent = keyStats.total_keys;
        document.getElementById('total-requests').textContent = formatNumber(accountStats.total_requests);
        
        // Update tokens stats
        const totalInputTokens = tokensStats.total.input_tokens || 0;
        const totalOutputTokens = tokensStats.total.output_tokens || 0;
        const totalTokens = tokensStats.total.total_tokens || 0;
        
        document.getElementById('total-input-tokens').innerHTML = formatLargeNumber(totalInputTokens) + '<span class="unit">tokens</span>';
        document.getElementById('total-output-tokens').innerHTML = formatLargeNumber(totalOutputTokens) + '<span class="unit">tokens</span>';
        document.getElementById('total-tokens').innerHTML = formatLargeNumber(totalTokens) + '<span class="unit">tokens</span>';
        
        // Update tokens chart
        updateTokensChart(tokensStats);
        
        // Update account usage table
        updateAccountUsageTable(accountUsageStats);
        
    } catch (error) {
        console.error('Error loading dashboard:', error);
        if (!handleAuthError(error)) {
            alert('加载数据失败');
        }
    }
}

// Update tokens chart
function updateTokensChart(tokensStats) {
    const ctx = document.getElementById('tokens-chart');
    if (!ctx) return;
    
    const daily = tokensStats.daily || [];
    const labels = daily.map(d => {
        const date = new Date(d.date);
        return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    });
    
    const inputTokensData = daily.map(d => d.input_tokens || 0);
    const outputTokensData = daily.map(d => d.output_tokens || 0);
    const totalTokensData = daily.map(d => d.total_tokens || 0);
    
    // Destroy existing chart if it exists
    if (tokensChart) {
        tokensChart.destroy();
    }
    
    tokensChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: '输入 Tokens',
                    data: inputTokensData,
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.1)',
                    tension: 0.1,
                    fill: true
                },
                {
                    label: '输出 Tokens',
                    data: outputTokensData,
                    borderColor: 'rgb(255, 99, 132)',
                    backgroundColor: 'rgba(255, 99, 132, 0.1)',
                    tension: 0.1,
                    fill: true
                },
                {
                    label: '总 Tokens',
                    data: totalTokensData,
                    borderColor: 'rgb(54, 162, 235)',
                    backgroundColor: 'rgba(54, 162, 235, 0.1)',
                    tension: 0.1,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'top',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + formatNumber(context.parsed.y);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return formatLargeNumber(value);
                        }
                    }
                }
            }
        }
    });
}

// Update account usage table
function updateAccountUsageTable(accountUsageStats) {
    const container = document.getElementById('account-usage-table');
    if (!container) return;
    
    const accounts = accountUsageStats.accounts || [];
    
    if (accounts.length === 0) {
        container.innerHTML = '<p style="color: #666; padding: 1rem;">暂无使用数据</p>';
        return;
    }
    
    const tableHtml = `
        <table class="usage-table" style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr>
                    <th>账号名称</th>
                    <th>状态</th>
                    <th>输入 Tokens</th>
                    <th>输出 Tokens</th>
                    <th>总 Tokens</th>
                    <th>请求数</th>
                    <th>总请求数（全部）</th>
                    <th>最后使用</th>
                </tr>
            </thead>
            <tbody>
                ${accounts.map(acc => `
                    <tr>
                        <td><strong>${acc.account_name}</strong></td>
                        <td>
                            <span class="status-badge ${acc.is_active ? 'status-active' : 'status-inactive'}">
                                ${acc.is_active ? '活跃' : '停用'}
                            </span>
                            <span class="status-badge ${acc.is_healthy ? 'status-healthy' : 'status-inactive'}" style="margin-left: 0.5rem;">
                                ${acc.is_healthy ? '健康' : '异常'}
                            </span>
                        </td>
                        <td><span class="token-badge">${formatNumber(acc.input_tokens)}</span></td>
                        <td><span class="token-badge">${formatNumber(acc.output_tokens)}</span></td>
                        <td><strong>${formatNumber(acc.total_tokens)}</strong></td>
                        <td>${formatNumber(acc.requests)}</td>
                        <td>${formatNumber(acc.total_requests_all_time)}</td>
                        <td>${acc.last_used ? new Date(acc.last_used).toLocaleString('zh-CN') : '从未使用'}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = tableHtml;
}

// Load accounts
async function loadAccounts() {
    try {
        const accounts = await fetchWithAuth(`${API_BASE}/admin/accounts`).then(r => r.json());
        const tableHtml = `
            <table>
                <thead>
                    <tr>
                        <th>名称</th>
                        <th>状态</th>
                        <th>健康</th>
                        <th>请求数</th>
                        <th>Token数</th>
                        <th>最后使用</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${accounts.map(acc => `
                        <tr>
                            <td>${acc.name}</td>
                            <td><span class="status-badge ${acc.is_active ? 'status-active' : 'status-inactive'}">
                                ${acc.is_active ? '活跃' : '停用'}
                            </span></td>
                            <td><span class="status-badge ${acc.is_healthy ? 'status-healthy' : 'status-inactive'}">
                                ${acc.is_healthy ? '健康' : '异常'}
                            </span></td>
                            <td>${acc.total_requests || 0}</td>
                            <td>${acc.total_tokens || 0}</td>
                            <td>${acc.last_used ? new Date(acc.last_used).toLocaleString() : '-'}</td>
                            <td>
                                <button class="btn btn-primary" onclick="refreshAccountToken(${acc.id})" style="margin-right: 0.5rem;">刷新Token</button>
                                <button class="btn" onclick="viewAccountStats(${acc.id})" style="margin-right: 0.5rem;">统计</button>
                                <button class="btn btn-danger" onclick="deleteAccount(${acc.id})">删除</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        document.getElementById('accounts-table').innerHTML = tableHtml;
    } catch (error) {
        console.error('Error loading accounts:', error);
    }
}

// Load API keys
async function loadApiKeys() {
    try {
        const keys = await fetchWithAuth(`${API_BASE}/admin/api-keys`).then(r => r.json());
        const tableHtml = `
            <table>
                <thead>
                    <tr>
                        <th>名称</th>
                        <th>密钥</th>
                        <th>状态</th>
                        <th>请求数</th>
                        <th>最后使用</th>
                        <th>过期时间</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${keys.map(key => `
                        <tr>
                            <td>${key.name}</td>
                            <td><code>${key.key}</code></td>
                            <td><span class="status-badge ${key.is_active ? 'status-active' : 'status-inactive'}">
                                ${key.is_active ? '活跃' : '停用'}
                            </span></td>
                            <td>${key.total_requests}</td>
                            <td>${key.last_used ? new Date(key.last_used).toLocaleString() : '-'}</td>
                            <td>${key.expires_at ? new Date(key.expires_at).toLocaleString() : '永久'}</td>
                            <td>
                                ${key.is_active ? `<button class="btn" onclick="revokeKey(${key.id})">吊销</button>` : ''}
                                <button class="btn btn-danger" onclick="deleteKey(${key.id})">删除</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        document.getElementById('keys-table').innerHTML = tableHtml;
    } catch (error) {
        console.error('Error loading API keys:', error);
    }
}

// Modal functions
function showAddAccountModal() {
    document.getElementById('add-account-modal').classList.add('show');
}

function showAddKeyModal() {
    document.getElementById('add-key-modal').classList.add('show');
}

function showUploadJsonModal() {
    // 重置表单
    document.getElementById('upload-json-form').reset();
    document.getElementById('upload-json-alert').innerHTML = '';
    document.getElementById('upload-json-modal').classList.add('show');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('show');
}

// Form submissions
document.getElementById('add-account-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    
    // Convert empty strings to null
    if (!data.profile_arn) data.profile_arn = null;
    if (!data.notes) data.notes = null;
    data.requests_per_minute = parseInt(data.requests_per_minute);
    
    try {
        const response = await fetchWithAuth(`${API_BASE}/admin/accounts`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            closeModal('add-account-modal');
            e.target.reset();
            loadAccounts();
            alert('账号添加成功！');
        } else {
            const error = await response.json();
            alert('添加失败: ' + error.detail);
        }
    } catch (error) {
        alert('添加失败: ' + error.message);
    }
});

document.getElementById('add-key-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    
    // Convert empty strings to null
    if (!data.description) data.description = null;
    if (!data.expires_days) data.expires_days = null;
    else data.expires_days = parseInt(data.expires_days);
    
    data.requests_per_minute = parseInt(data.requests_per_minute);
    data.requests_per_day = parseInt(data.requests_per_day);
    data.is_admin = data.is_admin === 'true';  // Convert checkbox to boolean
    
    try {
        const response = await fetchWithAuth(`${API_BASE}/admin/api-keys`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            const result = await response.json();
            closeModal('add-key-modal');
            e.target.reset();
            loadApiKeys();
            alert('API密钥创建成功！\n密钥: ' + result.key + '\n\n请妥善保存，此密钥只显示一次！');
        } else {
            const error = await response.json();
            alert('创建失败: ' + error.detail);
        }
    } catch (error) {
        if (!handleAuthError(error)) {
            alert('创建失败: ' + error.message);
        }
    }
});

// Upload JSON form submission
document.getElementById('upload-json-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const alertDiv = document.getElementById('upload-json-alert');
    alertDiv.innerHTML = '<div class="alert alert-success">正在处理...</div>';
    
    const formData = new FormData(e.target);
    const fileInput = document.getElementById('upload-json-file');
    const file = fileInput.files[0];
    
    if (!file) {
        alertDiv.innerHTML = '<div class="alert alert-error">请选择 JSON 文件</div>';
        return;
    }
    
    // 验证文件类型
    if (!file.name.endsWith('.json')) {
        alertDiv.innerHTML = '<div class="alert alert-error">请选择 JSON 文件</div>';
        return;
    }
    
    // 读取文件内容并添加到 FormData
    formData.append('json_file', file);
    
    try {
        const apiKey = getApiKey();
        if (!apiKey) {
            window.location.href = '/admin/login';
            return;
        }
        
        const response = await fetch(`${API_BASE}/admin/accounts/upload-json`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${apiKey}`
            },
            body: formData
        });
        
        if (response.status === 401 || response.status === 403) {
            clearApiKey();
            window.location.href = '/admin/login';
            return;
        }
        
        const result = await response.json();
        
        if (response.ok) {
            alertDiv.innerHTML = '<div class="alert alert-success">账号添加成功！正在刷新 Token...</div>';
            closeModal('upload-json-modal');
            e.target.reset();
            loadAccounts();
            
            // 显示成功信息
            setTimeout(() => {
                alert(`账号添加成功！\n\n账号名称: ${result.account.name}\n账号ID: ${result.account.id}\n\nToken 已自动刷新！`);
            }, 500);
        } else {
            alertDiv.innerHTML = `<div class="alert alert-error">添加失败: ${result.detail || '未知错误'}</div>`;
        }
    } catch (error) {
        console.error('Upload error:', error);
        alertDiv.innerHTML = `<div class="alert alert-error">上传失败: ${error.message}</div>`;
    }
});

// Delete functions
async function deleteAccount(id) {
    if (!confirm('确定要删除此账号吗？')) return;
    
    try {
        const response = await fetchWithAuth(`${API_BASE}/admin/accounts/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadAccounts();
            alert('账号已删除');
        } else {
            alert('删除失败');
        }
    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}

async function deleteKey(id) {
    if (!confirm('确定要删除此API密钥吗？')) return;
    
    try {
        const response = await fetchWithAuth(`${API_BASE}/admin/api-keys/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadApiKeys();
            alert('API密钥已删除');
        } else {
            alert('删除失败');
        }
    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}

async function revokeKey(id) {
    if (!confirm('确定要吊销此API密钥吗？')) return;
    
    try {
        const response = await fetchWithAuth(`${API_BASE}/admin/api-keys/${id}/revoke`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadApiKeys();
            alert('API密钥已吊销');
        } else {
            alert('吊销失败');
        }
    } catch (error) {
        alert('吊销失败: ' + error.message);
    }
}

// Refresh account token
async function refreshAccountToken(id) {
    if (!confirm('确定要刷新此账号的 Token 吗？')) return;
    
    try {
        const response = await fetchWithAuth(`${API_BASE}/admin/accounts/${id}/refresh-token`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            alert(`Token 刷新成功！\n过期时间: ${result.expires_in} 秒`);
            loadAccounts();
        } else {
            const error = await response.json();
            alert('刷新失败: ' + error.detail);
        }
    } catch (error) {
        alert('刷新失败: ' + error.message);
    }
}

// View account statistics
async function viewAccountStats(id) {
    try {
        const response = await fetchWithAuth(`${API_BASE}/admin/accounts/${id}/stats`);
        if (response.ok) {
            const stats = await response.json();
            
            // Format token info
            let tokenInfo = '未缓存';
            if (stats.token_info && stats.token_info.cached) {
                const expiresAt = stats.token_info.expires_at ? new Date(stats.token_info.expires_at).toLocaleString() : '未知';
                tokenInfo = `已缓存 (${stats.token_info.is_valid ? '有效' : '已过期'})\n过期时间: ${expiresAt}`;
            }
            
            // Format auto recover time
            let autoRecover = stats.auto_recover_at ? new Date(stats.auto_recover_at).toLocaleString() : '无';
            
            // Format error info
            let errorInfo = `错误计数: ${stats.error_count || 0}/5`;
            if (stats.last_error_time) {
                errorInfo += `\n最后错误: ${new Date(stats.last_error_time).toLocaleString()}`;
            }
            if (stats.health_check_error) {
                errorInfo += `\n错误信息: ${stats.health_check_error}`;
            }
            
            const message = `账号统计信息: ${stats.account_name}

状态:
- 活跃: ${stats.is_active ? '是' : '否'}
- 健康: ${stats.is_healthy ? '是' : '否'}

使用统计:
- 总请求数: ${stats.total_requests || 0}
- 总Token数: ${stats.total_tokens || 0}
- 最后使用: ${stats.last_used ? new Date(stats.last_used).toLocaleString() : '从未使用'}

限流设置:
- 每分钟请求限制: ${stats.requests_per_minute || 0}
- 当前RPM: ${stats.current_rpm || 0}
- RPM重置时间: ${stats.rpm_reset_at ? new Date(stats.rpm_reset_at).toLocaleString() : '无'}

健康检查:
${errorInfo}
- 最后检查: ${stats.last_health_check ? new Date(stats.last_health_check).toLocaleString() : '从未检查'}
- 自动恢复时间: ${autoRecover}

Token信息:
${tokenInfo}

创建时间: ${new Date(stats.created_at).toLocaleString()}
更新时间: ${new Date(stats.updated_at).toLocaleString()}`;
            
            alert(message);
        } else {
            const error = await response.json();
            alert('获取统计失败: ' + error.detail);
        }
    } catch (error) {
        alert('获取统计失败: ' + error.message);
    }
}

// Close modal when clicking outside
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('show');
        }
    });
});

// Load dashboard on page load
document.addEventListener('DOMContentLoaded', () => {
    // Check if API key exists
    const apiKey = getApiKey();
    if (!apiKey) {
        // 重定向到登录页面
        window.location.href = '/admin/login';
        return;
    }
    
    // 验证 API key 是否有效
    fetchWithAuth(`${API_BASE}/admin/stats/accounts`)
        .then(() => {
            // API key 有效，加载仪表盘
            loadDashboard();
        })
        .catch((error) => {
            // API key 无效，重定向到登录页面
            console.error('API key validation failed:', error);
            clearApiKey();
            window.location.href = '/admin/login';
        });
});
