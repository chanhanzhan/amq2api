// Admin panel JavaScript

// API base URL
const API_BASE = '';

// Logout function
async function logout() {
    if (!confirm('确定要登出吗？')) return;
    
    try {
        await fetch(`${API_BASE}/admin/logout`, { method: 'POST' });
        window.location.href = '/admin/login-page';
    } catch (error) {
        console.error('Logout error:', error);
        window.location.href = '/admin/login-page';
    }
}

// Handle authentication errors
function handleAuthError(error) {
    if (error.message && error.message.includes('401')) {
        alert('会话已过期，请重新登录');
        window.location.href = '/admin/login-page';
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

// Load dashboard stats
async function loadDashboard() {
    try {
        const [accountStats, keyStats] = await Promise.all([
            fetch(`${API_BASE}/admin/stats/accounts`).then(r => r.json()),
            fetch(`${API_BASE}/admin/stats/api-keys`).then(r => r.json())
        ]);
        
        document.getElementById('total-accounts').textContent = accountStats.total_accounts;
        document.getElementById('active-accounts').textContent = accountStats.active_accounts;
        document.getElementById('total-keys').textContent = keyStats.total_keys;
        document.getElementById('total-requests').textContent = accountStats.total_requests;
    } catch (error) {
        console.error('Error loading dashboard:', error);
        if (!handleAuthError(error)) {
            alert('加载数据失败');
        }
    }
}

// Load accounts
async function loadAccounts() {
    try {
        const accounts = await fetch(`${API_BASE}/admin/accounts`).then(r => r.json());
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
                            <td>${acc.total_requests}</td>
                            <td>${acc.total_tokens}</td>
                            <td>${acc.last_used ? new Date(acc.last_used).toLocaleString() : '-'}</td>
                            <td>
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
        const keys = await fetch(`${API_BASE}/admin/api-keys`).then(r => r.json());
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
        const response = await fetch(`${API_BASE}/admin/accounts`, {
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
    
    try {
        const response = await fetch(`${API_BASE}/admin/api-keys`, {
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
        alert('创建失败: ' + error.message);
    }
});

// Delete functions
async function deleteAccount(id) {
    if (!confirm('确定要删除此账号吗？')) return;
    
    try {
        const response = await fetch(`${API_BASE}/admin/accounts/${id}`, {
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
        const response = await fetch(`${API_BASE}/admin/api-keys/${id}`, {
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
        const response = await fetch(`${API_BASE}/admin/api-keys/${id}/revoke`, {
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
    loadDashboard();
});
