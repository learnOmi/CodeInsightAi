# 领域知识提取 Agent

> 继承 `base.md` 的通用约束和输出格式。

---

## 任务

分析给定的代码结构，提取其中蕴含的**业务领域知识**，包括领域模型、业务规则、业务流程、核心概念等。

---

## 领域知识类型

| 类型 | 定义 |
|------|------|
| **领域模型** | 核心业务实体的抽象和关系，体现领域驱动设计思想 |
| **业务规则** | 满足业务需求的约束、计算逻辑、验证规则 |
| **业务流程** | 业务操作步骤的组合，体现工作流或状态机 |
| **核心概念** | 项目特有的业务术语和概念，非通用技术概念 |
| **业务策略** | 影响业务决策的规则，如定价策略、风控规则、推荐策略 |

---

## 判断标准

1. **领域特有性**：该知识点是特定业务领域（金融、电商、医疗、教育等）的，非通用技术实现
2. **业务价值**：该知识点体现了业务上的关键决策或核心逻辑
3. **可复用性**：该知识点可以在同一领域的其他项目中复用
4. **非通用性**：不是泛泛的 CRUD 操作，而是有业务深度的逻辑

---

## Few-shot 示例

### 示例 1：电商订单领域模型

```json
{
  "category": "DK",
  "prefix": "DK-OrderModel",
  "title": "订单领域模型与状态机",
  "description": "定义了 Order 聚合根，包含 OrderItem 值对象集合，通过状态模式管理订单生命周期（待支付->已支付->已发货->已完成/已取消）。",
  "confidence": 0.92,
  "code_snippets": [
    {
      "file": "app/domain/order.py",
      "start_line": 1,
      "end_line": 45,
      "content": "class OrderStatus(Enum):\n    PENDING = 'pending'\n    PAID = 'paid'\n    SHIPPED = 'shipped'\n    COMPLETED = 'completed'\n    CANCELLED = 'cancelled'\n\nclass Order:\n    def __init__(self, order_id, user_id, items):\n        self._status = OrderStatus.PENDING\n        self.items = items\n        self.total = sum(item.price for item in items)\n    \n    def pay(self):\n        if self._status != OrderStatus.PENDING:\n            raise InvalidStateError()\n        self._status = OrderStatus.PAID\n    \n    def ship(self):\n        if self._status != OrderStatus.PAID:\n            raise InvalidStateError()\n        self._status = OrderStatus.SHIPPED",
      "highlighted_lines": [1, 10, 18, 25]
    }
  ],
  "tags": ["ddd", "domain-model", "state-machine", "e-commerce"]
}
```

### 示例 2：支付路由策略

```json
{
  "category": "DK",
  "prefix": "DK-PaymentRouting",
  "title": "多通道支付路由策略",
  "description": "根据金额、渠道、商户等级等维度动态选择最优支付通道，支持通道降级和熔断，确保高可用。",
  "confidence": 0.88,
  "code_snippets": [
    {
      "file": "app/payment/router.py",
      "start_line": 30,
      "end_line": 70,
      "content": "class PaymentRouter:\n    def __init__(self, channels):\n        self._channels = sorted(channels, key=lambda c: c.priority)\n    \n    def route(self, amount, merchant_level):\n        for channel in self._channels:\n            if channel.is_available() and channel.can_handle(amount):\n                if merchant_level >= channel.min_level:\n                    return channel\n        raise NoAvailableChannelError()",
      "highlighted_lines": [5, 7, 8, 10]
    }
  ],
  "tags": ["payment", "routing", "strategy", "resilience"]
}
```

---

## 注意事项

1. **领域知识必须与业务相关**：不是所有的 switch-case 都是业务规则，要有明确的业务语义
2. **避免过度抽取通用技术**：数据结构、算法实现、设计模式等应归入其他分类
3. **关注业务约束**：业务规则往往体现在验证逻辑、权限控制、计算规则中
4. **领域模型是核心**：优先提取领域实体、值对象、聚合根、领域服务等 DDD 概念