class Resource:
    def __init__(self, id, name, count=1, completed=0, scores=None):
        self.id = id
        self.name = name
        self.count = count
        self.completed = completed
        self.scores = scores or []
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'count': self.count,
            'completed': self.completed,
            'scores': self.scores
        }
    
    @classmethod
    def from_dict(cls, data):
        if not data:
            return None
        
        return cls(
            id=data.get('id'),
            name=data.get('name'),
            count=data.get('count', 1),
            completed=data.get('completed', 0),
            scores=data.get('scores', [])
        )
