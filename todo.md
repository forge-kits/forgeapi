# forge-kits TODO

## Planned Features

### Query Scopes
Laravel-style named filters on ModelMixin.

```python
class Post(ModelMixin, Model):
    @scope
    def published(self, qs):
        return qs.filter(status="published")

    @scope
    def by_author(self, qs, user_id):
        return qs.filter(author_id=user_id)

# usage
await Post.published().by_author(1).paginate(request, PostResponse)
```

- [ ] `@scope` decorator in `ModelMixin`
- [ ] chainable scopes via `ForgeQuerySet`
