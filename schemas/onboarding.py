from pydantic import BaseModel, validator
from typing import List

# Predefined topics list
AVAILABLE_TOPICS = [
    "Science",
    "Technology",
    "Gaming",
    "Movies & TV Shows",
    "Music",
    "Sports",
    "Health & Fitness",
    "Food & Cooking",
    "Travel",
    "Fashion",
    "Art & Design",
    "Photography",
    "Books & Literature",
    "History",
    "Politics",
    "Finance & Investing",
    "Education",
    "Nature & Environment",
    "Space & Astronomy",
    "DIY & Crafts",
    "Comedy",
    "Memes & Humor",
    "Anime & Manga",
    "Cars & Motorcycles",
    "Relationships & Dating",
    "Mental Health",
    "Meditation & Mindfulness",
    "Business & Entrepreneurship",
    "Science Fiction & Fantasy",
    "True Crime",
    "Parenting",
    "Gardening",
    "Fitness Challenges",
    "Coding & Programming",
    "Pets & Animals",
    "Photography Tips",
    "Gaming Strategies",
    "Streaming & Podcasts",
    "Startups & Tech News",
    "Productivity Hacks",
    "Environment & Climate Change",
    "Art Tutorials",
    "Social Justice",
    "Home Improvement",
    "Career Advice",
    "Makeup & Beauty",
    "Language Learning",
    "Philosophy",
    "Festivals & Events",
    "Motivational Stories"
]

class OnboardingRequest(BaseModel):
    topics: List[str]

    @validator('topics')
    def validate_topics(cls, v):
        if len(v) < 3:
            raise ValueError('You must select at least 3 topics')
        if len(v) > 50:
            raise ValueError('You can select up to 50 topics')
        
        # Check if all topics are valid
        invalid_topics = [topic for topic in v if topic not in AVAILABLE_TOPICS]
        if invalid_topics:
            raise ValueError(f'Invalid topics: {", ".join(invalid_topics)}')
        
        # Check for duplicates
        if len(v) != len(set(v)):
            raise ValueError('Duplicate topics are not allowed')
        
        return v

class OnboardingResponse(BaseModel):
    message: str
    selected_topics: List[str]
    total_topics: int

class AvailableTopicsResponse(BaseModel):
    topics: List[str]
    total_count: int 