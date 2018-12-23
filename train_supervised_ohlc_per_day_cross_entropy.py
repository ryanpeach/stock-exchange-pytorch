import argparse
import datetime
import logging
import os
import warnings
warnings.filterwarnings('ignore')

import torch
from torch.utils.data import DataLoader

from functools import partial
from ignite.engine import Events, create_supervised_trainer, create_supervised_evaluator
from supervised import get_metrics, Classifier, TickersData, device


def binary_target(non_binary_y, threshold):
    if threshold >= 0.0:
        binary_y = non_binary_y >= threshold
    else:
        binary_y = non_binary_y < threshold

    return binary_y


def get_tickers():
    from download_daily_data import my_list

    my_list = list(my_list)
    pickle_files = list(map(lambda x: x.split('_')[0], os.listdir('data/ohlc_processed/')))
    valid_tickers = [item for item in my_list if item in pickle_files]

    return valid_tickers


def get_input_target(args):
    def get_shift_data_point_transform_dims():
        # + 1 comes from today's shift
        shift_dim = len(list(range(-args.max_shift_forward, -args.min_shift_forward,
                                   args.max_shift_forward // args.shift_increment))) + 1

        # Usually, ohlc+volume = 5
        data_point_dim = args.data_point_dim
        # Number of different sklearn.pipelines.FeatureUnion, found in process_and_save_ohlc_daily.py
        transform_dim = args.transform_dim

        expected_dim = shift_dim * data_point_dim * transform_dim * len_valid_tickers
        example_row_dim = train_set[0][0].shape[0]

        assert example_row_dim == expected_dim, '{} vs {}'.format(example_row_dim, expected_dim)

        return shift_dim, data_point_dim, transform_dim

    binary_transform = partial(binary_target, threshold=args.threshold)
    valid_tickers = get_tickers()

    train_set = TickersData(valid_tickers, '_train.pickle', y_transform=binary_transform)
    test_set = TickersData(valid_tickers, '_test.pickle', y_transform=binary_transform)
    train_dl = DataLoader(train_set, num_workers=1, batch_size=args.batch_size)
    test_dl = DataLoader(test_set, num_workers=1, batch_size=args.batch_size)

    non_binary_y_train = torch.DoubleTensor(train_set.read_in_pickles('_y_train.pickle'))
    non_binary_y_test = torch.DoubleTensor(test_set.read_in_pickles('_y_test.pickle'))

    len_valid_tickers = len(valid_tickers)
    shift_dim_data_point_dim_transform_dim = get_shift_data_point_transform_dims()

    return train_dl, test_dl, non_binary_y_train, non_binary_y_test, len_valid_tickers, shift_dim_data_point_dim_transform_dim


def compute_return_distribution_on_pred(model, dataloader, non_binary_y, threshold=0.5):
    '''
    :param model: original model
    :param dataloader: iterable of x, y in binary
    :param non_binary_y: non-binary version of y
    :param threshold: default to 0.5 for output
    :return: mean and stdev of actual outcomes from predicted true by the model

    It concats outputs altogether first, then run the mask.
    This is not an efficient way of using memory, but EpochMetric handles
    things similarly, so leave it as is for now...
    '''
    so_far = torch.tensor([], dtype=torch.float64, device=device)
    for x, _ in dataloader:
        out = model(x.cuda())
        so_far = torch.cat([so_far, out], dim=0)

    assert non_binary_y.shape == so_far.shape, '::RAISE:: y.shape: {}, pred.shape: {}'.format(
        non_binary_y.shape, so_far.shape)

    mask = so_far.ge(threshold)
    relevant_pred = torch.masked_select(so_far, mask)

    if relevant_pred.nelement() == 0:
        return 0.0, -1.0

    y_value = torch.masked_select(non_binary_y, mask)
    distribution = relevant_pred * y_value

    return distribution.mean(), distribution.std()


def register_evaluators(trainer,
                        evaluator_train,
                        evaluator_test,
                        train_dl,
                        test_dl,
                        model,
                        non_binary_y_train,
                        non_binary_y_test):

    @trainer.on(Events.EPOCH_COMPLETED)
    def log_training_results(trainer):
        if trainer.state.epoch % args.print_every == 0:

            mean_stat, std_stat = compute_return_distribution_on_pred(model, train_dl, non_binary_y_train)
            evaluator_train.run(train_dl)
            metrics = evaluator_train.state.metrics

            msg1 = "Training Results  - Epoch: {} Accuracy: {:.5f}, BCE: {:.5f}, F1 Score: {:.5f}, ROC_AUC: {:.5f}".format(
                trainer.state.epoch, metrics['accuracy'], metrics['bce'], metrics['f1_score'], metrics['roc_auc'],)
            msg2 = "Training Results  - Epoch: {} Precision: {:.5f}, Recall: {:.5f}".format(
                trainer.state.epoch, metrics['precision'], metrics['recall'],)
            msg3 = '{},train,{:.5f},{:.5f},{}'.format(
                trainer.state.epoch, mean_stat, std_stat, metrics["conf_matrix"].ravel())
            print("Training Results  - Epoch: {} Confusion Matrix: \n{}".format(
                trainer.state.epoch, metrics['conf_matrix'], ))

            print_and_log(msg1, bce_logger)
            print_and_log(msg2, bce_logger)
            print_and_log(msg3, stat_logger)

    @trainer.on(Events.EPOCH_COMPLETED)
    def log_validation_results(trainer):
        if trainer.state.epoch % args.print_every == 0:

            mean_stat, std_stat = compute_return_distribution_on_pred(model, test_dl, non_binary_y_test)
            evaluator_test.run(test_dl)
            metrics = evaluator_test.state.metrics

            msg1 = "Validation Results  - Epoch: {} Accuracy: {:.5f}, BCE: {:.5f}, F1 Score: {:.5f}, ROC_AUC: {:.5f}".format(
                trainer.state.epoch, metrics['accuracy'], metrics['bce'], metrics['f1_score'], metrics['roc_auc'],)
            msg2 = "Validation Results  - Epoch: {} Precision: {:.5f}, Recall: {:.5f}".format(
                trainer.state.epoch, metrics['precision'], metrics['recall'],)
            msg3 = '{},test,{:.5f},{:.5f},{}'.format(
                trainer.state.epoch, mean_stat, std_stat, metrics["conf_matrix"].ravel())
            print("Validation Results  - Epoch: {} Confusion Matrix: \n{}".format(
            trainer.state.epoch, metrics['conf_matrix'], ))

            print_and_log(msg1, bce_logger)
            print_and_log(msg2, bce_logger)
            print_and_log(msg3, stat_logger)


def print_and_log(msg, logger):
    print(f'{msg}')
    logger.info(f'{msg}')


parser = argparse.ArgumentParser(description='Hyper-parameters for the training')
parser.add_argument('--max_epoch',       default=600, type=int)
parser.add_argument('--print_every',     default=50, type=int)
parser.add_argument('--batch_size',      default=64, type=int)
parser.add_argument('--data_point_dim',  default=5, type=int)
parser.add_argument('--transform_dim',   default=4, type=int)
parser.add_argument('--shift_increment', default=3, type=int)
parser.add_argument('--min_shift_forward',      default=3,  type=int)
parser.add_argument('--max_shift_forward',      default=10, type=int)
parser.add_argument('--threshold',       default=0.02, type=float)
parser.add_argument('--learning_rate',   default=0.01,  type=float)

args = parser.parse_args()

try:
    os.makedirs('logs')
except OSError:
    print('--- log folder exists')

FILE_NAME_BASIC_INFO = 'logs/training_bce_{}_{}.log'.format(
    '_'.join(str(datetime.datetime.now()).split(' ')), args.threshold)
FILE_NAME_STAT = 'logs/training_bce_{}_stat_{}.log'.format(
    '_'.join(str(datetime.datetime.now()).split(' ')), args.threshold)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

bce_logger = logging.getLogger(__name__)
bce_logger.setLevel(logging.INFO)
stat_logger = logging.getLogger(__name__+'_stat')
stat_logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(FILE_NAME_BASIC_INFO)
file_handler.setFormatter(formatter)
bce_logger.addHandler(file_handler)

file_handler_stat = logging.FileHandler(FILE_NAME_STAT)
stat_logger.addHandler(file_handler_stat)


def main(args):
    print_and_log('--- Starting training: {}'.format(datetime.datetime.now()), bce_logger)

    train_dl, test_dl, non_binary_y_train, non_binary_y_test, num_tickers, shift_data_point_transform_dim = \
        get_input_target(args)
    non_binary_y_train, non_binary_y_test = non_binary_y_train.to(device), non_binary_y_test.to(device)

    shift_dim, data_point_dim, transform_dim = shift_data_point_transform_dim
    output_dim = non_binary_y_train.shape[-1]

    model = Classifier(num_tickers,
                       data_point_dim=data_point_dim,
                       shift_dim=shift_dim,
                       transform_dim=transform_dim,
                       output_dim=output_dim)
    # criterion = CustomLoss()
    criterion = torch.nn.BCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate, weight_decay=1e-6)

    trainer = create_supervised_trainer(model, optimizer, criterion, device=device)
    evaluator_train = create_supervised_evaluator(
        model, metrics=get_metrics(non_binary_y_train), device=device)
    evaluator_test = create_supervised_evaluator(
        model, metrics=get_metrics(non_binary_y_test), device=device)

    register_evaluators(trainer,
                        evaluator_train,
                        evaluator_test,
                        train_dl,
                        test_dl,
                        model,
                        non_binary_y_train,
                        non_binary_y_test)

    trainer.run(train_dl, max_epochs=args.max_epoch)

    print_and_log('--- Ending training: {}'.format(datetime.datetime.now()), bce_logger)


if __name__ == '__main__':
    main(args)