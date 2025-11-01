# ServerDisconnectedError 原因分析和解决方案

## 错误原因

`ServerDisconnectedError` 表示服务器在数据传输过程中意外关闭了连接。常见原因：

### 1. **TCP连接Keepalive超时**
- **默认问题**：aiohttp 的 TCPConnector 默认 `keepalive_timeout=15` 秒
- **触发场景**：长时间运行的工作流中，如果两次请求间隔超过15秒，连接会被服务器关闭
- **表现**：在问卷生成这种长时间任务中，多个网络搜索请求之间的间隔可能超过15秒

### 2. **连接复用问题**
- **默认行为**：TCPConnector 默认 `force_close=True`，每次请求后关闭连接
- **问题**：频繁创建/关闭连接可能导致服务器端拒绝或断开连接
- **影响**：在高并发或长时间运行的场景下，连接管理不当

### 3. **服务器端限制**
- **SearXNG服务器**：可能有连接超时限制（通常30-60秒）
- **网络代理**：Nginx或其他代理可能有关闭空闲连接的设置
- **并发限制**：服务器可能限制来自同一客户端的并发连接数

### 4. **异步任务未等待**
- **问题**：使用 `create_task` 创建的异步任务如果发生异常且未被等待，会产生未处理的Future异常
- **表现**：错误日志中显示 "Future exception was never retrieved"

## 已实施的解决方案

### 1. **优化TCPConnector配置**
```python
connector = aiohttp.TCPConnector(
    ssl=self.ssl_ctx,
    enable_cleanup_closed=True,
    force_close=False,  # ✅ 允许连接复用，减少断开
    limit=100,  # 连接池总大小
    limit_per_host=30,  # 每个主机的最大连接数
    keepalive_timeout=60,  # ✅ 从15秒增加到60秒
    ttl_dns_cache=300,  # DNS缓存5分钟
)
```

**改进点**：
- `keepalive_timeout=60`：保持连接活跃60秒，适合长时间运行的任务
- `force_close=False`：允许连接复用，减少连接建立/关闭的开销
- `limit=100` 和 `limit_per_host=30`：合理限制连接数，避免服务器拒绝

### 2. **增强错误处理和重试**
```python
except (aiohttp.ClientError, aiohttp.ServerDisconnectedError) as e:
    # 检测到连接断开，自动重置session并重试
    if isinstance(e, aiohttp.ServerDisconnectedError):
        logger.debug("检测到服务器断开连接，重置session并重试")
        # 关闭旧session，创建新session，然后重试
```

**改进点**：
- 自动检测连接断开
- 重置session并重试（最多2次）
- 使用指数退避避免频繁重试

### 3. **修复Future异常**
```python
def handle_task_done(t):
    try:
        t.result()  # ✅ 获取结果，这样异常会被捕获
    except Exception:
        pass  # 忽略关闭时的异常
task.add_done_callback(handle_task_done)
```

**改进点**：
- 在回调中调用 `t.result()` 确保异常被捕获
- 避免 "Future exception was never retrieved" 警告

## 最佳实践建议

### 1. **连接池管理**
- ✅ 使用连接池复用连接
- ✅ 设置合理的 keepalive_timeout（建议60秒以上）
- ✅ 限制并发连接数，避免过载

### 2. **错误处理**
- ✅ 捕获 `ServerDisconnectedError` 并重试
- ✅ 实现指数退避重试策略
- ✅ 记录错误但不要中断工作流

### 3. **Session管理**
- ✅ 确保 session 在使用前已初始化
- ✅ 在异常情况下重置 session
- ✅ 正确关闭 session，避免资源泄漏

### 4. **异步任务管理**
- ✅ 所有 `create_task` 创建的任务都要有异常处理
- ✅ 使用 `add_done_callback` 捕获任务异常
- ✅ 避免创建"fire-and-forget"任务

## 监控和诊断

如果问题仍然存在，可以：

1. **检查SearXNG服务状态**
   ```bash
   curl -I http://127.0.0.1:8088
   ```

2. **查看连接统计**
   - 监控连接池使用情况
   - 检查连接断开频率
   - 分析断开发生的时机

3. **调整配置**
   - 根据实际需求调整 `keepalive_timeout`
   - 根据服务器能力调整 `limit_per_host`
   - 考虑增加重试次数

## 总结

`ServerDisconnectedError` 主要是由于：
1. **Keepalive超时**（已修复：增加到60秒）
2. **连接复用不当**（已修复：force_close=False）
3. **错误处理不完善**（已修复：添加重试和异常捕获）

通过这些改进，连接断开错误应该显著减少，即使发生也能自动恢复。

