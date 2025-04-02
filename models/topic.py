class Topic:
    def __init__(self, id, name, resources=None):
        self.id = id
        self.name = name
        self.resources = resources or []
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'resources': [resource.to_dict() for resource in self.resources] if self.resources else []
        }
    
    @classmethod
    def from_dict(cls, data):
        from models.resource import Resource
        if not data:
            return None
        
        resources = [Resource.from_dict(r) for r in data.get('resources', [])] if data.get('resources') else []
        return cls(
            id=data.get('id'),
            name=data.get('name'),
            resources=resources
        )
