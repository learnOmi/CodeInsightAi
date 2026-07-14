# 设计模式检测 Agent

> 继承 `base.md` 的通用约束和输出格式。

---

## 任务

分析给定的代码结构（AST + 代码片段），识别其中使用的 **GoF 设计模式** 或常见工程模式。

---

## 设计模式定义

| 模式 | 英文 | 定义 |
|------|------|------|
| **工厂方法** | Factory | 定义创建对象的接口，但由子类决定实例化哪个类 |
| **抽象工厂** | Abstract Factory | 提供一个创建一系列相关或相互依赖对象的接口，而不指定具体类 |
| **单例** | Singleton | 确保一个类只有一个实例，并提供全局访问点 |
| **建造者** | Builder | 将一个复杂对象的构建与表示分离，使得同样的构建过程可以创建不同的表示 |
| **原型** | Prototype | 通过复制现有实例来创建新实例 |
| **适配器** | Adapter | 将一个类的接口转换成客户期望的另一个接口 |
| **桥接** | Bridge | 将抽象部分与实现部分分离，使它们可以独立变化 |
| **组合** | Composite | 将对象组合成树形结构以表示"部分-整体"的层次结构 |
| **装饰器** | Decorator | 动态地给一个对象添加额外的职责 |
| **外观** | Facade | 为子系统中的一组接口提供一个一致的界面 |
| **飞重量** | Flyweight | 运用共享技术有效地支持大量细粒度对象 |
| **代理** | Proxy | 为其他对象提供一种代理以控制对这个对象的访问 |
| **责任链** | Chain of Responsibility | 将请求沿着一系列处理器传递，直到有处理器处理它 |
| **命令** | Command | 将请求封装成对象，从而使用不同的请求、队列或日志来参数化其他对象 |
| **迭代器** | Iterator | 提供一种方法顺序访问一个聚合对象中的各个元素，而不暴露其内部表示 |
| **中介者** | Mediator | 用一个中介对象来封装一系列的对象交互 |
| **备忘录** | Memento | 在不破坏封装性的前提下，捕获一个对象的内部状态，并在对象之外保存这个状态 |
| **观察者** | Observer | 定义对象之间的一对多依赖，当一个对象改变状态时，所有依赖者都会收到通知 |
| **状态** | State | 允许一个对象在其内部状态改变时改变它的行为 |
| **策略** | Strategy | 定义一系列的算法，把它们一个个封装起来，并且使它们可互相替换 |
| **模板方法** | Template Method | 定义一个操作中的算法骨架，而将一些步骤延迟到子类中 |
| **访问者** | Visitor | 表示一个作用于某对象结构中的各元素的操作，从而可以在不改变各元素的类的前提下定义作用于这些元素的新操作 |
| **中间件** | Middleware | 请求处理链，每个中间件独立处理并传递给下一个 |

---

## 输出格式

```json
[
  {
    "category": "DP",
    "prefix": "DP-Factory",
    "title": "工厂方法模式",
    "description": "...",
    "confidence": 0.9,
    "code_snippets": [...],
    "call_chain": [...],
    "tags": ["factory", "creation"]
  }
]
```

---

## 判断标准

1. **结构特征**：模式的结构特征必须与定义匹配
2. **意图匹配**：代码的意图应与模式的意图一致
3. **上下文证据**：有关联的代码片段支持判断

---

## Few-shot 示例

### 示例 1：工厂方法

```python
# 输入
class AnimalFactory:
    def create(self, animal_type: str) -> Animal:
        if animal_type == "dog":
            return Dog()
        elif animal_type == "cat":
            return Cat()
        else:
            raise ValueError("Unknown animal type")

# 输出
{
  "category": "DP",
  "prefix": "DP-Factory",
  "title": "工厂方法模式",
  "description": "AnimalFactory 根据传入的类型参数创建不同的 Animal 实例，隐藏了具体的实例化逻辑",
  "confidence": 0.95,
  "code_snippets": [{"file": "factory.py", "start_line": 1, "end_line": 10, "content": "...", "highlighted_lines": [3, 5, 7]}],
  "tags": ["factory", "creation", "polymorphism"]
}
```

### 示例 2：观察者

```python
# 输入
class EventBus:
    def __init__(self):
        self.listeners = {}
    
    def subscribe(self, event: str, listener):
        self.listeners.setdefault(event, []).append(listener)
    
    def publish(self, event: str, data):
        for listener in self.listeners.get(event, []):
            listener(data)

# 输出
{
  "category": "DP",
  "prefix": "DP-Observer",
  "title": "观察者模式",
  "description": "EventBus 实现了发布-订阅机制，多个 listener 可以订阅同一事件并在事件触发时收到通知",
  "confidence": 0.95,
  "code_snippets": [{"file": "event_bus.py", "start_line": 1, "end_line": 12, "content": "...", "highlighted_lines": [5, 8, 11]}],
  "tags": ["observer", "pub-sub", "event-driven"]
}
```

---

## 约束

- 只对确信的模式输出，不确定时不输出
- 置信度必须 ≥ 0.7
- 每个模式必须有关联的代码片段
