## Summary

<!-- Brief description of the changes -->

## Related Issues

<!-- Link to related issues using "Fixes #123" or "Relates to #123" -->

Fixes #

## Use Case(s)

<!-- Which use case(s) does this PR implement? e.g., DL-1, P-2 -->

- [ ]

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ New feature (non-breaking change that adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to change)
- [ ] 📝 Documentation update
- [ ] 🔧 Refactoring (no functional changes)
- [ ] 🧪 Test update

## Layer(s) Affected

<!-- Check all that apply -->

- [ ] Layer 1: Data Layer (`packages/data-layer/`)
- [ ] Layer 2: Agents (`packages/agents/`)
- [ ] Layer 3: CLI (`packages/cli/`)
- [ ] Documentation (`docs/`)

## Checklist

### Code Quality

- [ ] My code follows the project's architecture rules (dependencies flow downward only)
- [ ] I have not added skip-layer imports (CLI → data-layer is forbidden)
- [ ] I have followed existing patterns in the codebase
- [ ] I have added comments where the logic isn't self-evident

### Testing

- [ ] I have added unit tests for new functionality
- [ ] I have added integration tests where applicable
- [ ] All new and existing tests pass locally
- [ ] Test coverage meets minimum threshold (≥80%)

### Documentation

- [ ] I have updated relevant documentation
- [ ] I have updated the CHANGELOG if applicable

### Authority Rules (if writing to Neo4j)

- [ ] Writes go through CanonKeeper only
- [ ] Authority checks are in place in `middleware/auth.py`

## Test Plan

<!-- How did you test these changes? -->

```bash
# Commands to run tests
cd packages/<layer> && pytest

# CI validation scripts
python scripts/require_tests_for_code_changes.py --base <base_sha>
python scripts/check_layer_dependencies.py
```

## Screenshots (if applicable)

<!-- Add screenshots for UI changes -->

## Additional Notes

<!-- Any additional context or notes for reviewers -->
