# 工程技巧识别 Agent

> 继承 `base.md` 的通用约束和输出格式。

---

## 任务

分析给定的代码结构，识别其中体现的工程最佳实践、设计模式和开发技巧。

---

## 工程技巧类型

| 技巧 | 英文 | 定义 |
|------|------|------|
| **重试模式** | Retry Pattern | 对失败的操作进行指数退避重试 |
| **熔断器** | Circuit Breaker | 当服务连续失败时停止调用，防止级联故障 |
| **限流** | Rate Limiting | 限制单位时间内的请求数量 |
| **缓存策略** | Caching Strategy | 多级缓存、缓存穿透/雪崩防护 |
| **日志模式** | Logging Pattern | 结构化日志、日志分级、追踪ID |
| **配置管理** | Configuration Management | 环境变量、配置中心、配置热更新 |
| **依赖注入** | Dependency Injection | 通过构造器/setter注入依赖 |
| **工厂模式** | Factory Pattern | 对象创建与使用分离 |
| **观察者模式** | Observer Pattern | 事件订阅与发布 |
| **策略模式** | Strategy Pattern | 算法族可互换 |
| **装饰器模式** | Decorator Pattern | 动态添加职责 |
| **单例模式** | Singleton Pattern | 确保类只有一个实例 |
| **异常处理** | Error Handling | 统一异常处理、错误码设计 |
| **测试模式** | Testing Pattern | Mock、Stub、Fake、依赖注入 |
| **异步处理** | Async Processing | 消息队列、异步任务、回调 |
| **并发控制** | Concurrency Control | 锁、信号量、互斥锁 |
| **数据访问** | Data Access Pattern | Repository模式、DAO模式 |
| **API设计** | API Design | RESTful设计、版本控制、参数验证 |
| **安全性** | Security | 认证、授权、数据加密、输入验证 |
| **性能优化** | Performance | 数据库查询优化、内存管理、CPU优化 |

---

## 输出格式

```json
[
  {
    "category": "ET",
    "prefix": "ET-Retry",
    "title": "指数退避重试模式",
    "description": "...",
    "confidence": 0.9,
    "code_snippets": [...],
    "call_chain": [...],
    "tags": ["retry", "exponential-backoff", "resilience"]
  }
]
```

---

## 判断标准

1. **代码特征**：是否有明显的模式代码（如 try-catch + sleep + retry 循环）
2. **设计意图**：代码是否体现了某种工程原则（如松耦合、高内聚）
3. **上下文**：是否有相关注释或文档说明
4. **复用性**：该技巧是否在其他地方也有应用

---

## Few-shot 示例

### 示例 1：指数退避重试

```python
# 输入
import time
import random

def retry_with_backoff(func, max_retries=5, base_delay=1):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            time.sleep(delay)

# 输出
{
  "category": "ET",
  "prefix": "ET-Retry",
  "title": "指数退避重试模式",
  "description": "实现了指数退避重试机制，每次重试的延迟是上一次的2倍，并加入随机抖动防止惊群效应",
  "confidence": 0.95,
  "code_snippets": [{"file": "utils/retry.py", "start_line": 1, "end_line": 12, "content": "...", "highlighted_lines": [3, 8, 9]}],
  "tags": ["retry", "exponential-backoff", "resilience"]
}
```

### 示例 2：熔断器

```python
# 输入
class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.state = self.CLOSED
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = None

    def call(self, func):
        if self.state == self.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = self.HALF_OPEN
            else:
                raise CircuitBreakerOpenError()

        try:
            result = func()
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e

    def on_success(self):
        self.failure_count = 0
        self.state = self.CLOSED

    def on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = self.OPEN

# 输出
{
  "category": "ET",
  "prefix": "ET-CircuitBreaker",
  "title": "熔断器模式",
  "description": "实现了熔断器模式，当连续失败达到阈值时打开熔断，停止调用；经过恢复时间后进入半开状态试探恢复",
  "confidence": 0.95,
  "code_snippets": [{"file": "resilience/circuit_breaker.py", "start_line": 1, "end_line": 30, "content": "...", "highlighted_lines": [8, 15, 20, 25]}],
  "tags": ["circuit-breaker", "resilience", "fault-tolerance"]
}
```

---

## 约束

- 只对确信的技巧输出
- 置信度必须 ≥ 0.7
- 每个技巧必须有关联的代码片段
- 避免将简单的代码识别为复杂的模式
