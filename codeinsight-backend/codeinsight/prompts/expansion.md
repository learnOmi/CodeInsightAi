# 拓展内容生成 Agent

> 为已提取的知识点生成多维度的拓展内容，帮助开发者深入理解每个知识点。

---

## 任务

为给定的知识点生成 5 个维度的拓展内容，以 JSON 格式返回。

---

## 输入信息

**知识点标题**：{title}
**知识点分类**：{category}
**知识点描述**：{description}

---

## 拓展维度

| 维度 | 说明 | 要求 |
|------|------|------|
| **principle** | 核心原理和技术本质 | 100-200 字，解释该模式/技术的原理 |
| **applicable_scenarios** | 适用场景列表 | 3-5 个，每个场景 20-50 字 |
| **best_practices** | 最佳实践建议 | 3-5 条，每条 20-50 字 |
| **related_patterns** | 关联的技术/模式 | 3-5 个，每个附带简要说明 |
| **learning_resources** | 学习资源推荐 | 3-5 个，每个包含 title、url、type（book/article/video/course） |

---

## 输出格式

```json
{
    "principle": "string",
    "applicable_scenarios": ["string"],
    "best_practices": ["string"],
    "related_patterns": ["string"],
    "learning_resources": [
        {"title": "string", "url": "string", "type": "book|article|video|course"}
    ]
}
```

---

## 示例

### 示例 1：工厂方法模式

**知识点标题**：Factory Method Pattern
**知识点分类**：设计模式
**知识点描述**：通过工厂方法封装对象创建逻辑，将实例化延迟到子类，符合开闭原则。

**输出**：
```json
{
    "principle": "工厂方法模式通过定义一个创建对象的接口，让子类决定实例化哪个类。它将对象的创建和使用分离，客户端只需依赖抽象接口而非具体实现。核心在于通过继承机制将实例化逻辑下放到子类，实现控制反转。",
    "applicable_scenarios": [
        "类无法预知需要创建哪种对象时",
        "类希望由子类指定创建的对象时",
        "需要将对象的创建逻辑从使用逻辑中分离时"
    ],
    "best_practices": [
        "工厂方法返回抽象类型而非具体类型",
        "参数化工厂方法可接受参数决定创建哪种对象",
        "结合依赖注入容器管理工厂实例",
        "为工厂方法定义清晰的命名约定"
    ],
    "related_patterns": [
        "Abstract Factory — 工厂方法用于创建单个产品，抽象工厂创建产品族",
        "Template Method — 工厂方法是模板方法的一种特殊形式",
        "Singleton — 工厂方法通常实现为单例",
        "Prototype — 工厂方法返回新实例，原型模式返回克隆"
    ],
    "learning_resources": [
        {"title": "GoF 设计模式", "url": "https://en.wikipedia.org/wiki/Factory_method_pattern", "type": "article"},
        {"title": "Refactoring Guru — Factory Method", "url": "https://refactoring.guru/design-patterns/factory-method", "type": "article"},
        {"title": "Head First Design Patterns", "url": "https://www.oreilly.com/library/view/head-first-design/9781492077992/", "type": "book"}
    ]
}
```

### 示例 2：事件驱动架构

**知识点标题**：Event-Driven Architecture
**知识点分类**：架构设计
**知识点描述**：基于事件的生产-消费模型，通过事件总线解耦组件，支持异步处理和可扩展性。

**输出**：
```json
{
    "principle": "事件驱动架构基于事件的产生、检测、消费和响应。组件之间不直接通信，而是通过事件总线发布和订阅事件，实现松耦合。事件可以是状态变更、用户操作或外部触发的信号，支持同步和异步处理模式。",
    "applicable_scenarios": [
        "需要高可扩展性和低耦合的微服务系统",
        "实时数据处理和流式计算场景",
        "跨多个服务的业务状态变更通知",
        "需要审计日志和事件溯源的系统"
    ],
    "best_practices": [
        "事件设计应包含足够的上下文信息，避免接收者额外查询",
        "使用幂等的事件处理逻辑，支持重试",
        "为事件定义清晰的版本策略",
        "采用死信队列处理失败事件",
        "监控事件吞吐量和处理延迟"
    ],
    "related_patterns": [
        "CQRS — 命令查询职责分离常与事件驱动配合使用",
        "Event Sourcing — 以事件序列作为系统状态",
        "Saga — 分布式事务的事件驱动编排模式",
        "Observer — 事件驱动的本地变体"
    ],
    "learning_resources": [
        {"title": "Building Event-Driven Microservices", "url": "https://www.oreilly.com/library/view/building-event-driven-microservices/9781492057888/", "type": "book"},
        {"title": "Event-Driven Architecture — AWS", "url": "https://aws.amazon.com/event-driven-architecture/", "type": "article"},
        {"title": "Martin Fowler — Event Sourcing", "url": "https://martinfowler.com/eaaDev/EventSourcing.html", "type": "article"}
    ]
}
```

---

## 质量标准

1. **principle** 应解释"为什么"而非"是什么"，揭示技术本质
2. **applicable_scenarios** 应具体，避免泛泛的"提高可维护性"式描述
3. **best_practices** 应可操作，给出具体建议而非笼统原则
4. **related_patterns** 需要说明关联关系（"与XX的区别"或"XX的补充"）
5. **learning_resources** 的 url 必须是真实有效的学习资源链接，type 必须为 book/article/video/course 之一
6. 仅返回 JSON，不要包含任何 Markdown 标记或说明文字