# -*- coding: utf-8 -*-
"""pneumoniafinal.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1H8mxr_kYoBOy2mxXB-_R4Sj1y16cgX3l
"""

# Import necessary libraries
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report
import tensorflow as tf
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Conv2D, MaxPooling2D, Flatten, Dense, Dropout, BatchNormalization
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.callbacks import ModelCheckpoint, EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.applications import EfficientNetB0
from tensorflow.keras.applications.efficientnet import preprocess_input
from google.colab import drive, files
from PIL import Image
import io

# Mount Google Drive
drive.mount('/content/drive')

# Define paths
base_path = '/content/drive/MyDrive/train'
normal_path = os.path.join(base_path, 'NORMAL')
pneumonia_path = os.path.join(base_path, 'PNEUMONIA')
covid_path = os.path.join(base_path, 'COVID19')

# Check dataset structure and count files
print("Dataset structure:")
print(f"Normal images: {len(os.listdir(normal_path))}")
print(f"Pneumonia images: {len(os.listdir(pneumonia_path))}")
print(f"Covid images: {len(os.listdir(covid_path))}")

# Analyze image dimensions from each class
def analyze_image_dimensions(folder_path, sample_size=100):
    files = os.listdir(folder_path)
    if len(files) > sample_size:
        files = np.random.choice(files, sample_size, replace=False)

    widths, heights = [], []
    for file in files:
        try:
            img_path = os.path.join(folder_path, file)
            img = Image.open(img_path)
            width, height = img.size
            widths.append(width)
            heights.append(height)
        except Exception as e:
            print(f"Error processing {file}: {e}")

    return widths, heights

# Sample and analyze images from each class
print("\nAnalyzing image dimensions...")
normal_widths, normal_heights = analyze_image_dimensions(normal_path)
pneumonia_widths, pneumonia_heights = analyze_image_dimensions(pneumonia_path)
covid_widths, covid_heights = analyze_image_dimensions(covid_path)

# Calculate average dimensions
avg_width = int(np.mean(normal_widths + pneumonia_widths + covid_widths))
avg_height = int(np.mean(normal_heights + pneumonia_heights + covid_heights))

print(f"Average image dimensions: {avg_width}x{avg_height}")

# Define target image size - rounded to multiples of 32 for better performance
target_size = (224, 224)  # Standard size for many pre-trained models
print(f"Target image size: {target_size}")

# Define batch size
batch_size = 32

# Create data generators with augmentation for training
train_datagen = ImageDataGenerator(
    preprocessing_function=preprocess_input,
    rotation_range=20,
    width_shift_range=0.2,
    height_shift_range=0.2,
    shear_range=0.2,
    zoom_range=0.2,
    horizontal_flip=True,
    fill_mode='nearest',
    validation_split=0.2  # 20% of data for validation
)

# Create data generators for training and validation
train_generator = train_datagen.flow_from_directory(
    base_path,
    target_size=target_size,
    batch_size=batch_size,
    class_mode='categorical',
    subset='training'
)

validation_generator = train_datagen.flow_from_directory(
    base_path,
    target_size=target_size,
    batch_size=batch_size,
    class_mode='categorical',
    subset='validation'
)

# Get class names
class_names = list(train_generator.class_indices.keys())
print(f"Class names: {class_names}")
num_classes = len(class_names)

# Handle class imbalance by using class weights
total_samples = len(os.listdir(normal_path)) + len(os.listdir(pneumonia_path)) + len(os.listdir(covid_path))
class_weights = {
    train_generator.class_indices['NORMAL']: total_samples / len(os.listdir(normal_path)),
    train_generator.class_indices['PNEUMONIA']: total_samples / len(os.listdir(pneumonia_path)),
    train_generator.class_indices['COVID19']: total_samples / len(os.listdir(covid_path))
}
print(f"Class weights: {class_weights}")

# Build the model using transfer learning with EfficientNetB0
def build_model():
    # Use EfficientNetB0 as the base model
    base_model = EfficientNetB0(weights='imagenet', include_top=False, input_shape=(target_size[0], target_size[1], 3))

    # Freeze the base model initially
    base_model.trainable = False

    model = Sequential([
        base_model,
        GlobalAveragePooling2D(),
        Dense(256, activation='relu'),
        BatchNormalization(),
        Dropout(0.5),
        Dense(128, activation='relu'),
        BatchNormalization(),
        Dropout(0.3),
        Dense(num_classes, activation='softmax')
    ])

    # Compile the model
    model.compile(
        optimizer=Adam(learning_rate=1e-3),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )

    return model

# Build the model
from tensorflow.keras.layers import GlobalAveragePooling2D
model = build_model()
model.summary()

# Create callbacks for model training
checkpoint_path = "/content/best_model.h5"
checkpoint = ModelCheckpoint(
    checkpoint_path,
    monitor='val_accuracy',
    verbose=1,
    save_best_only=True,
    mode='max'
)

early_stopping = EarlyStopping(
    monitor='val_accuracy',
    patience=10,
    verbose=1,
    restore_best_weights=True
)

reduce_lr = ReduceLROnPlateau(
    monitor='val_loss',
    factor=0.2,
    patience=5,
    verbose=1,
    min_lr=1e-6
)

callbacks = [checkpoint, early_stopping, reduce_lr]

# Train the model - first phase with frozen base model
history = model.fit(
    train_generator,
    epochs=20,
    validation_data=validation_generator,
    callbacks=callbacks,
    class_weight=class_weights
)

# Fine-tuning phase - unfreeze some layers of the base model
base_model = model.layers[0]
base_model.trainable = True

# Freeze the first 100 layers and fine-tune the remaining ones
for layer in base_model.layers[:100]:
    layer.trainable = False
for layer in base_model.layers[100:]:
    layer.trainable = True

# Recompile the model with a lower learning rate
model.compile(
    optimizer=Adam(learning_rate=1e-4),
    loss='categorical_crossentropy',
    metrics=['accuracy']
)

# Train with fine-tuning
fine_tune_history = model.fit(
    train_generator,
    epochs=30,
    validation_data=validation_generator,
    callbacks=callbacks,
    class_weight=class_weights
)

# If accuracy is still not sufficient, try another approach with a custom CNN
if max(history.history['val_accuracy'] + fine_tune_history.history['val_accuracy']) < 0.95:
    print("Trying a custom CNN architecture...")

    # Custom CNN model
    custom_model = Sequential([
        # First convolutional block
        Conv2D(32, (3, 3), activation='relu', input_shape=(target_size[0], target_size[1], 3), padding='same'),
        BatchNormalization(),
        Conv2D(32, (3, 3), activation='relu', padding='same'),
        BatchNormalization(),
        MaxPooling2D((2, 2)),
        Dropout(0.25),

        # Second convolutional block
        Conv2D(64, (3, 3), activation='relu', padding='same'),
        BatchNormalization(),
        Conv2D(64, (3, 3), activation='relu', padding='same'),
        BatchNormalization(),
        MaxPooling2D((2, 2)),
        Dropout(0.25),

        # Third convolutional block
        Conv2D(128, (3, 3), activation='relu', padding='same'),
        BatchNormalization(),
        Conv2D(128, (3, 3), activation='relu', padding='same'),
        BatchNormalization(),
        MaxPooling2D((2, 2)),
        Dropout(0.25),

        # Fourth convolutional block
        Conv2D(256, (3, 3), activation='relu', padding='same'),
        BatchNormalization(),
        Conv2D(256, (3, 3), activation='relu', padding='same'),
        BatchNormalization(),
        MaxPooling2D((2, 2)),
        Dropout(0.25),

        # Flatten and dense layers
        Flatten(),
        Dense(512, activation='relu'),
        BatchNormalization(),
        Dropout(0.5),
        Dense(256, activation='relu'),
        BatchNormalization(),
        Dropout(0.5),
        Dense(num_classes, activation='softmax')
    ])

    # Compile the model
    custom_model.compile(
        optimizer=Adam(learning_rate=1e-3),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )

    custom_model.summary()

    # Train the custom model
    custom_history = custom_model.fit(
        train_generator,
        epochs=50,
        validation_data=validation_generator,
        callbacks=callbacks,
        class_weight=class_weights
    )

    # Use the better performing model
    best_val_acc = max(history.history['val_accuracy'] + fine_tune_history.history['val_accuracy'])
    custom_best_val_acc = max(custom_history.history['val_accuracy'])

    if custom_best_val_acc > best_val_acc:
        print("Using the custom CNN model as it performed better")
        model = custom_model
    else:
        print("Using the transfer learning model as it performed better")
        model = load_model(checkpoint_path)
else:
    # Load the best model
    model = load_model(checkpoint_path)

# Evaluate the model on the validation set
validation_loss, validation_accuracy = model.evaluate(validation_generator)
print(f"Validation accuracy: {validation_accuracy:.4f}")

# If accuracy is still below 95%, try ensemble approach
if validation_accuracy < 0.95:
    print("Trying ensemble approach...")

    # Create a new EfficientNetB3-based model
    from tensorflow.keras.applications import EfficientNetB3

    def build_efficient_net_b3():
        base_model = EfficientNetB3(weights='imagenet', include_top=False, input_shape=(target_size[0], target_size[1], 3))
        base_model.trainable = False

        model = Sequential([
            base_model,
            GlobalAveragePooling2D(),
            Dense(512, activation='relu'),
            BatchNormalization(),
            Dropout(0.5),
            Dense(256, activation='relu'),
            BatchNormalization(),
            Dropout(0.3),
            Dense(num_classes, activation='softmax')
        ])

        model.compile(
            optimizer=Adam(learning_rate=1e-3),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )

        return model

    # Build and train the additional model
    model_b3 = build_efficient_net_b3()

    # Train with transfer learning
    b3_history = model_b3.fit(
        train_generator,
        epochs=20,
        validation_data=validation_generator,
        callbacks=callbacks,
        class_weight=class_weights
    )

    # Fine-tune
    base_model_b3 = model_b3.layers[0]
    base_model_b3.trainable = True

    for layer in base_model_b3.layers[:150]:
        layer.trainable = False

    model_b3.compile(
        optimizer=Adam(learning_rate=1e-4),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )

    # Fine-tune
    b3_fine_tune_history = model_b3.fit(
        train_generator,
        epochs=10,
        validation_data=validation_generator,
        callbacks=callbacks,
        class_weight=class_weights
    )

    # Save the second model
    model_b3.save('/content/model_b3.h5')

    # Function to make ensemble predictions
    def ensemble_predict(img, models):
        predictions = []
        for m in models:
            pred = m.predict(img)
            predictions.append(pred)

        # Average the predictions
        avg_pred = np.mean(predictions, axis=0)
        return avg_pred

    # Load both models for ensemble
    model_1 = load_model(checkpoint_path)
    model_2 = load_model('/content/model_b3.h5')
    ensemble_models = [model_1, model_2]

    # Testing the ensemble on validation data
    correct = 0
    total = 0

    for x, y in validation_generator:
        if total >= len(validation_generator.filenames):
            break

        ensemble_preds = ensemble_predict(x, ensemble_models)
        predicted_classes = np.argmax(ensemble_preds, axis=1)
        true_classes = np.argmax(y, axis=1)

        correct += np.sum(predicted_classes == true_classes)
        total += len(true_classes)

    ensemble_accuracy = correct / total
    print(f"Ensemble validation accuracy: {ensemble_accuracy:.4f}")

    # If ensemble performs better, use it
    if ensemble_accuracy > validation_accuracy:
        print("Using ensemble approach for predictions")
        use_ensemble = True
    else:
        print("Using the best single model for predictions")
        use_ensemble = False
        model = load_model(checkpoint_path)  # Use the best single model
else:
    use_ensemble = False

# Save the final model
model.save('/content/final_model.h5')

# Plot training history
def plot_training_history(history):
    plt.figure(figsize=(12, 4))

    plt.subplot(1, 2, 1)
    plt.plot(history.history['accuracy'])
    plt.plot(history.history['val_accuracy'])
    plt.title('Model Accuracy')
    plt.ylabel('Accuracy')
    plt.xlabel('Epoch')
    plt.legend(['Train', 'Validation'], loc='lower right')

    plt.subplot(1, 2, 2)
    plt.plot(history.history['loss'])
    plt.plot(history.history['val_loss'])
    plt.title('Model Loss')
    plt.ylabel('Loss')
    plt.xlabel('Epoch')
    plt.legend(['Train', 'Validation'], loc='upper right')

    plt.tight_layout()
    plt.show()

# Plot the training history
if 'custom_history' in locals():
    plot_training_history(custom_history)
else:
    # Combine histories
    combined_history = history
    combined_history.history['accuracy'] = history.history['accuracy'] + fine_tune_history.history['accuracy']
    combined_history.history['val_accuracy'] = history.history['val_accuracy'] + fine_tune_history.history['val_accuracy']
    combined_history.history['loss'] = history.history['loss'] + fine_tune_history.history['loss']
    combined_history.history['val_loss'] = history.history['val_loss'] + fine_tune_history.history['val_loss']
    plot_training_history(combined_history)

# Function to predict on new uploaded images
def predict_image(image_bytes):
    # Open the image
    img = Image.open(io.BytesIO(image_bytes))

    # Convert to RGB if it's not
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Resize the image
    img = img.resize(target_size)

    # Convert to array and add batch dimension
    img_array = np.array(img)
    img_array = np.expand_dims(img_array, axis=0)

    # Preprocess for the model
    img_array = preprocess_input(img_array)

    # Make prediction
    if use_ensemble:
        prediction = ensemble_predict(img_array, ensemble_models)
    else:
        prediction = model.predict(img_array)

    predicted_class_index = np.argmax(prediction[0])
    predicted_class = class_names[predicted_class_index]
    confidence = prediction[0][predicted_class_index] * 100

    return predicted_class, confidence

# Create upload button for image prediction
from IPython.display import display, HTML, clear_output
import ipywidgets as widgets

def predict_uploaded_file(change):
    clear_output()
    display(upload_button)

    if change.new:
        # Get the image bytes
        image_bytes = change.new[0]['content']

        # Make prediction
        predicted_class, confidence = predict_image(image_bytes)

        # Show the image
        img = Image.open(io.BytesIO(image_bytes))
        plt.figure(figsize=(6, 6))
        plt.imshow(img)
        plt.title(f'Prediction: {predicted_class} (Confidence: {confidence:.2f}%)')
        plt.axis('off')
        plt.show()

        print(f"Predicted class: {predicted_class}")
        print(f"Confidence: {confidence:.2f}%")

# Create the upload button
upload_button = widgets.FileUpload(
    accept='image/*',
    multiple=False,
    description='Upload Image'
)

upload_button.observe(predict_uploaded_file, names='value')
display(upload_button)
print("Upload an image to get a prediction")

# Display summary of the model architecture
print("\nModel Summary:")
model.summary()

print("\nModel training complete! Upload an image to test the model.")