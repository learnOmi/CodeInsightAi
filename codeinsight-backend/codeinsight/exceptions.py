"""
自定义异常

定义业务异常类及其全局异常处理器。
"""


class RepositoryPathExistsError(Exception):
    """仓库路径已存在的异常"""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"Repository path already exists: {path}")


class RepositoryNotFoundError(Exception):
    """仓库未找到的异常"""

    def __init__(self, repository_id: str):
        self.repository_id = repository_id
        super().__init__(f"Repository not found: {repository_id}")
