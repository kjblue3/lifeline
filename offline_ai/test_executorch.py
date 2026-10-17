
import torch
from executorch.exir import to_edge


# A tiny model to test the ExecuTorch export pipeline.
class TestModel(torch.nn.Module):
    def forward(self, x, y):
        return x + y


model = TestModel().eval()

# Example inputs define the expected input structure.
example_inputs = (
    torch.tensor([1.0, 2.0]),
    torch.tensor([3.0, 4.0]),
)

print("Step 1: Exporting PyTorch model...")

exported_program = torch.export.export(
    model,
    example_inputs,
)

print("Step 2: Converting to ExecuTorch...")

edge_program = to_edge(exported_program)
executorch_program = edge_program.to_executorch()

print("Step 3: Saving model...")

with open("test_model.pte", "wb") as f:
    f.write(executorch_program.buffer)

print("SUCCESS: test_model.pte created!")
