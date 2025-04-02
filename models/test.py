from datetime import datetime

class Test:
    def __init__(self, id, name, date=None, topics=None, progress=0):
        self.id = id
        self.name = name
        self.date = date
        self.topics = topics or []
        self.progress = progress
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'date': self.date,
            'topics': [topic.to_dict() for topic in self.topics] if self.topics else [],
            'progress': self.progress
        }
    
    @classmethod
    def from_dict(cls, data, subject_name=None):
        from models.topic import Topic
        if not data:
            return None
        
        topics = [Topic.from_dict(t) for t in data.get('topics', [])] if data.get('topics') else []
        test = cls(
            id=data.get('id'),
            name=data.get('name'),
            date=data.get('date'),
            topics=topics,
            progress=data.get('progress', 0)
        )
        
        # Additional properties
        test.subject_name = subject_name
        test.is_past = cls._is_past_test(data.get('date'))
        
        return test
    
    @staticmethod
    def _is_past_test(test_date):
        """Determine if a test is in the past"""
        if not test_date:
            return False
            
        try:
            test_date_obj = datetime.strptime(test_date, '%Y-%m-%d').date()
            today = datetime.now().date()
            return test_date_obj < today
        except (ValueError, TypeError):
            return False
